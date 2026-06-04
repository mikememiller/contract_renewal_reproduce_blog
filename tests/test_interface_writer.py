"""Syntax Corporation © 2026 — EBS Contract Renewal PAF — PDOI writer tests."""
from __future__ import annotations

import csv
from datetime import date
from decimal import Decimal

from ebs_contract_renewal_paf.interface_writer import (
    HEADER_COLS,
    LINE_COLS,
    PDOIInterfaceWriter,
)


def _agreement():
    return {"po_header_id": 33467, "vendor_id": 1717, "vendor_site_id": 4060,
            "currency_code": "USD", "agent_id": 25, "terms_id": 10003,
            "end_date": "2010-12-31"}


def _supplier():
    return {"vendor_id": 1717, "vendor_num": "8058", "vendor_name": "HVAC Express",
            "vendor_site_id": 4060, "purchasing_site_flag": "Y",
            "site_inactive_date": None}


def _extracted():
    return {"agreement_num": "4467", "quote_number": "HVX-RENEW-2026-4467",
            "currency": "USD", "proposed_total": 17920.0}


def _term():
    return {"new_effective_date": date(2011, 1, 1),
            "new_expiration_date": date(2013, 12, 31),
            "prior_expiration_date": date(2010, 12, 31),
            "term_months": 36, "exceptions": []}


def _coded():
    spec = [
        (1, "AC Filter", 11063, 200, 17.50, "AUTO", []),
        (2, "Thermostat - Cooling", 11505, 40, 31.50, "AUTO", []),
        (3, "Thermostat - Heating", 11503, 40, 31.50, "AUTO", []),
        (4, "Thermostat - Heat Pump", 11501, 20, 385.00, "HOLD",
         ["PRICE_ESCALATION_10.00PCT_$700.00"]),
        (5, "Fan Bearing", 11537, 30, 140.00, "AUTO", []),
    ]
    out = []
    for ln, item, iid, qty, price, status, exc in spec:
        out.append({
            "line_number": ln, "item_number": item, "inventory_item_id": iid,
            "description": item, "uom": "Each", "uom_code": "Ea",
            "category_id": 37, "category": "SUPPLIES.FACILITIES",
            "line_type_id": 1, "item_active": "Y",
            "new_unit_price": price, "estimated_qty": qty,
            "extended_amount": price * qty, "match_status": status,
            "exceptions": exc,
        })
    return out


def test_header_balances_to_line_extended_amounts():
    w = PDOIInterfaceWriter(org_id=204)
    w.add_renewal(_agreement(), _supplier(), _extracted(), _term(), _coded(),
                  "REN-X", 0.8)
    hdr = w.headers[0]
    line_sum = sum(Decimal(l["UNIT_PRICE"]) * Decimal(str(l["QUANTITY"]))
                   for l in w.lines)
    assert Decimal(hdr["AMOUNT_AGREED"]) == Decimal("17920.00")
    assert line_sum == Decimal(hdr["AMOUNT_AGREED"])


def test_header_references_existing_agreement_for_update():
    w = PDOIInterfaceWriter(org_id=204)
    w.add_renewal(_agreement(), _supplier(), _extracted(), _term(), _coded(),
                  "REN-X", 0.8)
    hdr = w.headers[0]
    assert hdr["ACTION"] == "UPDATE"
    assert hdr["PO_HEADER_ID"] == 33467           # renew by header id, not doc num
    assert hdr["DOCUMENT_TYPE_CODE"] == "BLANKET"
    assert hdr["APPROVAL_STATUS"] == "INCOMPLETE"  # buyer approves in EBS
    assert hdr["VENDOR_DOC_NUM"] == "HVX-RENEW-2026-4467"
    assert hdr["EFFECTIVE_DATE"] == "2011-01-01"
    assert hdr["EXPIRATION_DATE"] == "2013-12-31"


def test_lines_carry_uom_code_and_prices():
    w = PDOIInterfaceWriter(org_id=204)
    w.add_renewal(_agreement(), _supplier(), _extracted(), _term(), _coded(),
                  "REN-X", 0.8)
    assert len(w.lines) == 5
    assert all(l["UOM_CODE"] == "Ea" for l in w.lines)   # 'Each' -> 'Ea'
    l4 = next(l for l in w.lines if l["LINE_NUM"] == 4)
    assert l4["UNIT_PRICE"] == "385.00"
    assert l4["QUANTITY"] == 20
    # PO_LINES_INTERFACE has no ATTRIBUTE columns — per-line audit is in the
    # trace/QA report, not the interface contract.
    assert "ATTRIBUTE1" not in l4


def test_no_tax_line_at_agreement_level():
    # Unlike the AP invoice agent, a blanket price catalog has no TAX line.
    w = PDOIInterfaceWriter(org_id=204)
    w.add_renewal(_agreement(), _supplier(), _extracted(), _term(), _coded(),
                  "REN-X", 0.8)
    assert all(l["LINE_TYPE"] == "Goods" for l in w.lines)


def test_csv_column_order(tmp_path):
    w = PDOIInterfaceWriter(org_id=204)
    w.add_renewal(_agreement(), _supplier(), _extracted(), _term(), _coded(),
                  "REN-X", 0.8)
    hdr_csv, ln_csv = w.write(tmp_path)
    with open(hdr_csv) as f:
        assert next(csv.reader(f)) == HEADER_COLS
    with open(ln_csv) as f:
        assert next(csv.reader(f)) == LINE_COLS
