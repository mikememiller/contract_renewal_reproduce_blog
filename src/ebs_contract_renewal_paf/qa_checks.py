"""
================================================================================
 Syntax Corporation © 2026 — All Rights Reserved
--------------------------------------------------------------------------------
 Project : EBS Contract Renewal PAF — BPA Renewal Automation Agent
 Module  : qa_checks.py — pre-load data-quality validation gate
 Version : 1.0.0      Build : 2026.06.04      Date : 2026-06-04
--------------------------------------------------------------------------------
 Deterministic checks run AFTER the PDOI rows are built and BEFORE anything is
 written / loaded. Produces a structured QAReport (serialised to
 qa_report.json). Severity model:

   ERROR  -> the renewal is malformed; the load MUST be blocked.
   HOLD   -> well-formed but outside policy (escalation / term / item status);
             route to buyer approval.
   WARN   -> non-blocking anomaly worth surfacing.
   INFO   -> informational.

 "Bugs make me sad" — this gate is the last line of defence before EBS.
================================================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

CENT = Decimal("0.01")

ERROR = "ERROR"
HOLD = "HOLD"
WARN = "WARN"
INFO = "INFO"

VALID_ACTIONS = {"ADD", "UPDATE", "REPLACE"}
VALID_DOC_TYPES = {"BLANKET", "CONTRACT"}
REQUIRED_HEADER = [
    "BATCH_ID", "ORG_ID", "ACTION", "DOCUMENT_TYPE_CODE", "PO_HEADER_ID",
    "VENDOR_ID", "VENDOR_SITE_ID", "CURRENCY_CODE", "EFFECTIVE_DATE",
    "EXPIRATION_DATE", "AMOUNT_AGREED", "APPROVAL_STATUS",
]

# How each policy/term exception maps onto the QA severity model.
_ERROR_EXCEPTIONS = {"NO_MATCHING_AGREEMENT_LINE", "NON_POSITIVE_PRICE",
                     "MISSING_TERM_DATES", "TERM_END_NOT_AFTER_START"}


def _d(value: Any) -> Decimal:
    return Decimal(str(value))


def _severity_for(exc: str) -> str:
    """Classify an exception code as ERROR (malformed) or HOLD (policy)."""
    base = exc.split("_")[0]
    if exc in _ERROR_EXCEPTIONS:
        return ERROR
    # prefixes like PRICE_ESCALATION_*, COVERAGE_GAP_*, TERM_OVERLAP_*,
    # TERM_TOO_*, NO_BASELINE_PRICE -> HOLD
    _ = base
    return HOLD


@dataclass
class Finding:
    check: str
    severity: str
    passed: bool
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {"check": self.check, "severity": self.severity,
                "passed": self.passed, "detail": self.detail}


@dataclass
class QAReport:
    agreement_num: str | None
    findings: list[Finding] = field(default_factory=list)

    def add(self, check: str, severity: str, passed: bool, detail: str) -> None:
        self.findings.append(Finding(check, severity, passed, detail))

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if not f.passed and f.severity == ERROR]

    @property
    def holds(self) -> list[Finding]:
        return [f for f in self.findings if not f.passed and f.severity == HOLD]

    @property
    def loadable(self) -> bool:
        """True only if there are no ERROR or HOLD findings."""
        return not self.errors and not self.holds

    @property
    def status(self) -> str:
        if self.errors:
            return "FAIL"
        if self.holds:
            return "HOLD"
        return "PASS"

    def to_dict(self) -> dict[str, Any]:
        return {
            "agreement_num": self.agreement_num,
            "status": self.status,
            "loadable": self.loadable,
            "error_count": len(self.errors),
            "hold_count": len(self.holds),
            "findings": [f.to_dict() for f in self.findings],
        }


def validate_renewal(
    header: dict[str, Any],
    lines: list[dict[str, Any]],
    extracted: dict[str, Any],
    coded_lines: list[dict[str, Any]],
    term: dict[str, Any],
    agreement: dict[str, Any] | None = None,
    supplier: dict[str, Any] | None = None,
    conn: Any | None = None,
    org_id: int = 204,
) -> QAReport:
    """Run all QA checks for one renewed agreement. `conn` (optional
    EBSConnection) enables referential checks against live EBS."""
    report = QAReport(agreement_num=extracted.get("agreement_num"))

    # --- 1. required header fields --------------------------------------
    for col in REQUIRED_HEADER:
        val = header.get(col)
        report.add(f"header.{col}", ERROR, val not in (None, ""), f"{col}={val!r}")

    # --- 2. enum validity -----------------------------------------------
    action = header.get("ACTION")
    report.add("header.action_valid", ERROR, action in VALID_ACTIONS,
               f"action={action!r}")
    doc_type = header.get("DOCUMENT_TYPE_CODE")
    report.add("header.doc_type_valid", ERROR, doc_type in VALID_DOC_TYPES,
               f"doc_type={doc_type!r}")

    # --- 3. per-line arithmetic (extended = price * qty) ----------------
    for ln in lines:
        try:
            qty = _d(ln["QUANTITY"])
            price = _d(ln["UNIT_PRICE"])
        except Exception:
            report.add(f"line[{ln.get('LINE_NUM')}].arithmetic", ERROR, False,
                       "non-numeric quantity/price (a blanket renewal needs an "
                       "estimated annual quantity to value the agreement)")
            continue
        report.add(f"line[{ln.get('LINE_NUM')}].price_positive", ERROR,
                   price > 0, f"unit_price={price}")
        report.add(f"line[{ln.get('LINE_NUM')}].qty_positive", ERROR,
                   qty > 0, f"quantity={qty}")

    # --- 4. header balances to sum of line extended amounts -------------
    extended_sum = Decimal("0")
    balanceable = True
    for ln in lines:
        try:
            extended_sum += (_d(ln["UNIT_PRICE"]) * _d(ln["QUANTITY"]))
        except Exception:
            balanceable = False
            break
    if balanceable:
        extended_sum = extended_sum.quantize(CENT)
        hdr_amt = _d(header["AMOUNT_AGREED"]).quantize(CENT)
        report.add("header.balances_to_lines", ERROR,
                   abs(extended_sum - hdr_amt) <= CENT,
                   f"sum(line price*qty)={extended_sum} vs "
                   f"AMOUNT_AGREED={hdr_amt}")
    else:
        report.add("header.balances_to_lines", ERROR, False,
                   "cannot balance: a line has non-numeric price/quantity")

    # --- 5. reconciliation vs the quote's proposed total ----------------
    proposed = extracted.get("proposed_total")
    if proposed is not None and balanceable:
        ok = abs(_d(proposed).quantize(CENT) - extended_sum) <= CENT
        report.add("header.reconciles_quote_total", WARN, ok,
                   f"quote_total={proposed} vs computed={extended_sum}")

    # --- 6. policy exceptions per line -> ERROR / HOLD ------------------
    for cl in coded_lines:
        for exc in cl.get("exceptions", []):
            sev = _severity_for(exc)
            report.add(f"line[{cl.get('line_number')}].{exc}", sev, False,
                       f"status={cl.get('match_status')}; {exc}")
        # inactive item on a renewed line needs a buyer decision
        if cl.get("item_active") == "N":
            report.add(f"line[{cl.get('line_number')}].item_active", HOLD, False,
                       f"item {cl.get('item_number')!r} is inactive/"
                       "non-purchasable")

    # --- 7. term exceptions -> ERROR / HOLD -----------------------------
    for exc in term.get("exceptions", []):
        report.add(f"term.{exc}", _severity_for(exc), False,
                   f"term_months={term.get('term_months')}; {exc}")

    # --- 8. supplier site active (when supplier supplied) --------------
    if supplier is not None:
        report.add("supplier.purchasing_site", HOLD,
                   (supplier.get("purchasing_site_flag") == "Y"),
                   f"purchasing_site_flag={supplier.get('purchasing_site_flag')!r}")
        report.add("supplier.site_active", HOLD,
                   supplier.get("site_inactive_date") in (None, ""),
                   f"site_inactive_date={supplier.get('site_inactive_date')!r}")

    # --- 9. referential checks (only with a live connection) -----------
    if conn is not None:
        _referential_checks(report, header, term, org_id, conn)

    return report


def _referential_checks(report: QAReport, header: dict[str, Any],
                        term: dict[str, Any], org_id: int, conn: Any) -> None:
    """Validate against live EBS: the target agreement exists and is an approved
    BLANKET, and no successor agreement already exists (idempotency)."""
    po_header_id = header.get("PO_HEADER_ID")
    row = conn.query_one(
        "SELECT type_lookup_code, authorization_status "
        "FROM apps.po_headers_all WHERE po_header_id = :h AND org_id = :o",
        {"h": po_header_id, "o": org_id},
    )
    report.add("agreement.exists_blanket_approved", ERROR,
               bool(row and row.get("type_lookup_code") == "BLANKET"
                    and row.get("authorization_status") == "APPROVED"),
               f"target agreement po_header_id={po_header_id}: {row}")

    # idempotency: a successor BLANKET on/after the new effective date
    eff = term.get("new_effective_date")
    if eff is not None and header.get("VENDOR_ID"):
        dup = conn.query_one(
            "SELECT COUNT(*) AS n FROM apps.po_headers_all "
            "WHERE vendor_id = :v AND org_id = :o "
            "AND type_lookup_code = 'BLANKET' AND start_date >= :eff "
            "AND po_header_id <> :h",
            {"v": header.get("VENDOR_ID"), "o": org_id, "eff": eff,
             "h": po_header_id},
        )
        report.add("renewal.not_already_created", ERROR,
                   not (dup and dup["n"] > 0),
                   f"successor agreements found={dup}")
