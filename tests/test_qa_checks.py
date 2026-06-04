"""Syntax Corporation © 2026 — EBS Contract Renewal PAF — QA gate tests."""
from __future__ import annotations

from ebs_contract_renewal_paf.qa_checks import validate_renewal


def _header(total="7300.00"):
    return {"BATCH_ID": "REN_1", "ORG_ID": 204, "ACTION": "UPDATE",
            "DOCUMENT_TYPE_CODE": "BLANKET", "PO_HEADER_ID": 33467,
            "VENDOR_ID": 1717, "VENDOR_SITE_ID": 4060, "CURRENCY_CODE": "USD",
            "EFFECTIVE_DATE": "2011-01-01", "EXPIRATION_DATE": "2013-12-31",
            "AMOUNT_AGREED": total, "APPROVAL_STATUS": "INCOMPLETE"}


def _lines():
    return [
        {"LINE_NUM": 1, "UNIT_PRICE": "21.00", "QUANTITY": 100},
        {"LINE_NUM": 2, "UNIT_PRICE": "520.00", "QUANTITY": 10},
    ]


def _coded(status="AUTO", exceptions=None, item_active="Y"):
    return [
        {"line_number": 1, "match_status": "AUTO", "exceptions": [],
         "item_active": "Y", "item_number": "FILTER-A"},
        {"line_number": 2, "match_status": status,
         "exceptions": exceptions or [], "item_active": item_active,
         "item_number": "PUMP-C"},
    ]


def _term(exceptions=None):
    return {"new_effective_date": "2011-01-01",
            "new_expiration_date": "2013-12-31", "term_months": 36,
            "exceptions": exceptions or []}


def _extracted():
    return {"agreement_num": "4467", "proposed_total": 7300.0}


def _supplier():
    return {"purchasing_site_flag": "Y", "site_inactive_date": None}


def test_clean_renewal_passes():
    rpt = validate_renewal(_header(), _lines(), _extracted(), _coded(), _term(),
                           supplier=_supplier())
    assert rpt.status == "PASS", rpt.to_dict()
    assert rpt.loadable


def test_unbalanced_header_fails():
    rpt = validate_renewal(_header(total="9999.99"), _lines(), _extracted(),
                           _coded(), _term(), supplier=_supplier())
    assert rpt.status == "FAIL"
    assert any(f.check == "header.balances_to_lines" for f in rpt.errors)


def test_escalation_hold_blocks_load_without_error():
    rpt = validate_renewal(
        _header(), _lines(), _extracted(),
        _coded(status="HOLD", exceptions=["PRICE_ESCALATION_10.00PCT_$700.00"]),
        _term(), supplier=_supplier())
    assert rpt.status == "HOLD"
    assert not rpt.loadable
    assert not rpt.errors


def test_missing_required_field_fails():
    h = _header()
    h["VENDOR_ID"] = ""
    rpt = validate_renewal(h, _lines(), _extracted(), _coded(), _term(),
                           supplier=_supplier())
    assert not rpt.loadable
    assert any(f.check == "header.VENDOR_ID" for f in rpt.errors)


def test_no_matching_agreement_line_is_error():
    rpt = validate_renewal(
        _header(), _lines(), _extracted(),
        _coded(status="HOLD", exceptions=["NO_MATCHING_AGREEMENT_LINE"]),
        _term(), supplier=_supplier())
    assert rpt.status == "FAIL"
    assert any("NO_MATCHING_AGREEMENT_LINE" in f.check for f in rpt.errors)


def test_inactive_item_holds():
    rpt = validate_renewal(_header(), _lines(), _extracted(),
                           _coded(item_active="N"), _term(),
                           supplier=_supplier())
    assert rpt.status == "HOLD"
    assert any("item_active" in f.check for f in rpt.holds)


def test_term_too_long_holds():
    rpt = validate_renewal(_header(), _lines(), _extracted(), _coded(),
                           _term(exceptions=["TERM_TOO_LONG_60M"]),
                           supplier=_supplier())
    assert rpt.status == "HOLD"
    assert any("TERM_TOO_LONG" in f.check for f in rpt.holds)


def test_term_end_before_start_fails():
    rpt = validate_renewal(_header(), _lines(), _extracted(), _coded(),
                           _term(exceptions=["TERM_END_NOT_AFTER_START"]),
                           supplier=_supplier())
    assert rpt.status == "FAIL"


def test_inactive_supplier_site_holds():
    bad = {"purchasing_site_flag": "Y", "site_inactive_date": "2024-01-01"}
    rpt = validate_renewal(_header(), _lines(), _extracted(), _coded(), _term(),
                           supplier=bad)
    assert rpt.status == "HOLD"
    assert any(f.check == "supplier.site_active" for f in rpt.holds)


def test_zero_quantity_line_fails():
    bad_lines = [{"LINE_NUM": 1, "UNIT_PRICE": "21.00", "QUANTITY": 0},
                 {"LINE_NUM": 2, "UNIT_PRICE": "520.00", "QUANTITY": 10}]
    rpt = validate_renewal(_header(total="5200.00"), bad_lines, _extracted(),
                           _coded(), _term(), supplier=_supplier())
    assert not rpt.loadable
    assert any("qty_positive" in f.check for f in rpt.errors)
