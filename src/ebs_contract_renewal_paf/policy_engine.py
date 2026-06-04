"""
================================================================================
 Syntax Corporation © 2026 — All Rights Reserved
--------------------------------------------------------------------------------
 Project : EBS Contract Renewal PAF — BPA Renewal Automation Agent
 Module  : policy_engine.py — renewal price-escalation, term & validity policy
 Version : 1.0.0      Build : 2026.06.04      Date : 2026-06-04
--------------------------------------------------------------------------------
 The deterministic policy layer between the (probabilistic) extractor and the
 PDOI interface tables. Keeping policy OUT of the LLM is what makes the agent
 auditable. A line whose proposed renewal price breaches policy is flagged for
 buyer approval — the interface row is still built but the batch is held.

 Primary rule (per the engagement): price-escalation dual tolerance.
   A line is HELD only when the price increase breaches BOTH a percentage cap
   (contractual / CPI ceiling) AND a material annual-dollar impact floor. The
   floor stops trivial cent-level increases on cheap, high-volume items from
   holding the whole renewal, while still catching real over-escalation.

 Secondary checks (term contiguity, item/supplier validity) are evaluated by the
 QA gate (qa_checks.py); this module owns the per-line escalation decision and
 the GL/term coding helpers.

 Tolerances would normally come from contract terms / org config; here they are
 explicit module constants matching spec.yaml.
================================================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

# Price-increase ceiling per renewed line (e.g. a CPI / contractual cap).
ESCALATION_TOLERANCE_PCT = Decimal("7.0")
# Material annual-dollar impact floor (price delta x estimated annual qty).
ESCALATION_DOLLAR_FLOOR = Decimal("250.00")
# Maximum renewal term length, in whole months.
MAX_TERM_MONTHS = 36


@dataclass
class RenewalLineResult:
    line_number: int
    matched: bool
    auto_approve: bool
    exceptions: list[str] = field(default_factory=list)
    current_unit_price: Decimal | None = None
    new_unit_price: Decimal | None = None
    escalation_pct: Decimal | None = None
    dollar_impact: Decimal | None = None
    estimated_qty: Decimal | None = None
    extended_amount: Decimal | None = None


def _d(value: Any) -> Decimal:
    return Decimal(str(value))


def evaluate_renewal_line(quote_line: dict[str, Any],
                          agreement: dict[str, Any]) -> RenewalLineResult:
    """Evaluate one renewal quote line against the existing agreement line.

    auto_approve is True only when the line matches an agreement line and the
    proposed price is within escalation tolerance (or is a decrease).
    """
    result = RenewalLineResult(line_number=quote_line["line_number"],
                               matched=False, auto_approve=False)

    # --- 1. find the matching agreement line ----------------------------
    ag_line = next(
        (l for l in agreement["lines"]
         if l["line_num"] == quote_line.get("agreement_line_num")),
        None,
    )
    if ag_line is None:  # fall back to item-number match
        ag_line = next(
            (l for l in agreement["lines"]
             if l.get("item_number") == quote_line.get("item_number")),
            None,
        )
    if ag_line is None:
        result.exceptions.append("NO_MATCHING_AGREEMENT_LINE")
        return result

    new_price = _d(quote_line["new_unit_price"])
    current_price = _d(ag_line["current_unit_price"])
    est_qty = _d(quote_line.get("estimated_qty") or 0)
    result.current_unit_price = current_price
    result.new_unit_price = new_price
    result.estimated_qty = est_qty
    result.extended_amount = (new_price * est_qty)

    # --- 2. structural validity -----------------------------------------
    if new_price <= 0:
        result.exceptions.append("NON_POSITIVE_PRICE")
        return result  # malformed; do not attempt escalation math

    # --- 3. price-escalation dual tolerance -----------------------------
    if current_price > 0:
        esc_pct = (new_price - current_price) / current_price * 100
        result.escalation_pct = esc_pct.quantize(Decimal("0.01"))
        # Only positive escalation is a risk; decreases are always allowed.
        if esc_pct > 0:
            dollar_impact = (new_price - current_price) * est_qty
            result.dollar_impact = dollar_impact.quantize(Decimal("0.01"))
            if (esc_pct > ESCALATION_TOLERANCE_PCT
                    and dollar_impact > ESCALATION_DOLLAR_FLOOR):
                result.exceptions.append(
                    f"PRICE_ESCALATION_{esc_pct:.2f}PCT_${dollar_impact:.2f}")
    else:
        # No prior price to compare against -> needs a human to set a baseline.
        result.exceptions.append("NO_BASELINE_PRICE")

    result.matched = True
    result.auto_approve = len(result.exceptions) == 0
    return result


# ---------------------------------------------------------------------------
# Term coding
# ---------------------------------------------------------------------------

def _to_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()


def _months_between(start: date, end: date) -> int:
    """Whole months between two dates, inclusive of the end month boundary.

    e.g. 2011-01-01 .. 2013-12-31 -> 36 months.
    """
    months = (end.year - start.year) * 12 + (end.month - start.month)
    # if the end day completes the final month (or is the last day), count it
    if end.day >= start.day - 1:
        months += 1
    return months


def evaluate_term(quote: dict[str, Any],
                  agreement: dict[str, Any]) -> dict[str, Any]:
    """Assess the proposed renewal term for contiguity and length.

    Returns a dict with the parsed dates, term length in months, and a list of
    term-level exceptions (consumed by the QA gate).
    """
    new_eff = _to_date(quote.get("new_effective_date"))
    new_exp = _to_date(quote.get("new_expiration_date"))
    prior_exp = _to_date(agreement.get("end_date"))
    exceptions: list[str] = []

    if new_eff is None or new_exp is None:
        exceptions.append("MISSING_TERM_DATES")
        return {"new_effective_date": new_eff, "new_expiration_date": new_exp,
                "prior_expiration_date": prior_exp, "term_months": None,
                "exceptions": exceptions}

    if new_exp <= new_eff:
        exceptions.append("TERM_END_NOT_AFTER_START")

    term_months = _months_between(new_eff, new_exp)
    if term_months > MAX_TERM_MONTHS:
        exceptions.append(f"TERM_TOO_LONG_{term_months}M")

    # contiguity: new term should start the day after the prior term ends.
    if prior_exp is not None:
        gap_days = (new_eff - prior_exp).days
        if gap_days > 1:
            exceptions.append(f"COVERAGE_GAP_{gap_days}D")
        elif gap_days < 1:
            exceptions.append(f"TERM_OVERLAP_{1 - gap_days}D")

    return {"new_effective_date": new_eff, "new_expiration_date": new_exp,
            "prior_expiration_date": prior_exp, "term_months": term_months,
            "exceptions": exceptions}
