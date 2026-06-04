"""Syntax Corporation © 2026 — EBS Contract Renewal PAF — policy engine tests."""
from __future__ import annotations

from decimal import Decimal

from ebs_contract_renewal_paf.policy_engine import (
    evaluate_renewal_line,
    evaluate_term,
)


def _agreement(current=20.0, line_num=1, item="FILTER-A", end="2025-12-31"):
    return {"po_header_id": 990001, "end_date": end, "lines": [{
        "line_num": line_num, "item_number": item,
        "current_unit_price": current, "inventory_item_id": 1,
        "item_active": "Y",
    }]}


def _qline(new=21.0, qty=100, ag_line=1, item="FILTER-A"):
    return {"line_number": 1, "agreement_line_num": ag_line, "item_number": item,
            "estimated_qty": qty, "new_unit_price": new}


def test_within_tolerance_auto_approves():
    # 20.00 -> 21.00 = +5% < 7%, impact 1.00*100 = 100 < 250 floor
    r = evaluate_renewal_line(_qline(new=21.0, qty=100), _agreement())
    assert r.matched and r.auto_approve
    assert r.exceptions == []
    assert r.escalation_pct == Decimal("5")
    assert r.extended_amount == Decimal("2100.0")


def test_escalation_breaches_both_gates_holds():
    # 50 -> 60 = +20% > 7%, impact 10*80 = 800 > 250 -> HOLD
    r = evaluate_renewal_line(_qline(new=60.0, qty=80, item="BELT-B"),
                              _agreement(current=50.0, item="BELT-B"))
    assert not r.auto_approve
    assert any(e.startswith("PRICE_ESCALATION") for e in r.exceptions)


def test_high_pct_but_small_dollar_impact_passes():
    # +20% but impact 2*1 = 2 < 250 floor -> dual gate not breached -> AUTO
    r = evaluate_renewal_line(_qline(new=12.0, qty=1, item="X"),
                              _agreement(current=10.0, item="X"))
    assert r.auto_approve
    assert not any(e.startswith("PRICE_ESCALATION") for e in r.exceptions)


def test_large_dollar_but_low_pct_passes():
    # 500 -> 520 = +4% < 7% even though impact 20*100 = 2000 -> AUTO
    r = evaluate_renewal_line(_qline(new=520.0, qty=100, item="P"),
                              _agreement(current=500.0, item="P"))
    assert r.auto_approve


def test_price_decrease_always_auto():
    r = evaluate_renewal_line(_qline(new=15.0, qty=1000), _agreement(current=20.0))
    assert r.auto_approve
    assert r.escalation_pct < 0


def test_non_positive_price_is_exception():
    r = evaluate_renewal_line(_qline(new=0.0), _agreement())
    assert not r.auto_approve
    assert "NON_POSITIVE_PRICE" in r.exceptions


def test_no_matching_agreement_line():
    r = evaluate_renewal_line(_qline(ag_line=9, item="ZZZ"), _agreement())
    assert not r.matched
    assert "NO_MATCHING_AGREEMENT_LINE" in r.exceptions


def test_falls_back_to_item_number_match():
    r = evaluate_renewal_line(_qline(ag_line=None, item="FILTER-A"), _agreement())
    assert r.matched and r.auto_approve


def test_term_contiguous_36_months_clean():
    t = evaluate_term(
        {"new_effective_date": "2011-01-01", "new_expiration_date": "2013-12-31"},
        {"end_date": "2010-12-31"})
    assert t["term_months"] == 36
    assert t["exceptions"] == []


def test_term_too_long_holds():
    t = evaluate_term(
        {"new_effective_date": "2026-01-01", "new_expiration_date": "2030-12-31"},
        {"end_date": "2025-12-31"})
    assert any(e.startswith("TERM_TOO_LONG") for e in t["exceptions"])


def test_term_coverage_gap_flagged():
    t = evaluate_term(
        {"new_effective_date": "2026-06-01", "new_expiration_date": "2027-05-31"},
        {"end_date": "2025-12-31"})
    assert any(e.startswith("COVERAGE_GAP") for e in t["exceptions"])


def test_term_overlap_flagged():
    t = evaluate_term(
        {"new_effective_date": "2025-06-01", "new_expiration_date": "2026-05-31"},
        {"end_date": "2025-12-31"})
    assert any(e.startswith("TERM_OVERLAP") for e in t["exceptions"])


def test_term_end_before_start_flagged():
    t = evaluate_term(
        {"new_effective_date": "2026-12-31", "new_expiration_date": "2026-01-01"},
        {"end_date": "2025-12-31"})
    assert "TERM_END_NOT_AFTER_START" in t["exceptions"]


def test_term_missing_dates_flagged():
    t = evaluate_term({"new_effective_date": None, "new_expiration_date": None},
                      {"end_date": "2025-12-31"})
    assert "MISSING_TERM_DATES" in t["exceptions"]
