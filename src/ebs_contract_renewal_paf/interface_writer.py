"""
================================================================================
 Syntax Corporation © 2026 — All Rights Reserved
--------------------------------------------------------------------------------
 Project : EBS Contract Renewal PAF — BPA Renewal Automation Agent
 Module  : interface_writer.py — PDOI interface row builder + CSV writer
 Version : 1.0.0      Build : 2026.06.04      Date : 2026-06-04
--------------------------------------------------------------------------------
 Builds PO_HEADERS_INTERFACE / PO_LINES_INTERFACE rows in the column order
 expected by the EBS Purchasing Documents Open Interface (PDOI), consumed by the
 standard "Import Price Catalogs" program. Column names mirror the EBS data
 dictionary so the output drops straight into SQL*Loader / OIC without remapping.

 Renewal model:
   * ACTION = 'UPDATE' and PO_HEADER_ID references the EXISTING agreement, so the
     import renews/replaces the blanket's price catalog and term (DOCUMENT_NUM is
     an obsoleted stub on this instance — see docs/EBS_INTERFACE_CONTRACT.md).
   * APPROVAL_STATUS = 'INCOMPLETE' so the buyer reviews + approves the renewed
     agreement in EBS (the agent never auto-approves a contract).
   * UOM_CODE is resolved live ('Each' -> 'Ea'); UNIT_OF_MEASURE carries the name.

 Balancing rule (domain-appropriate): the header AMOUNT_AGREED equals the sum of
 line extended amounts (UNIT_PRICE x QUANTITY). Tax is NOT applied at the
 agreement level in EBS (it is derived at release/invoice), so there is no TAX
 line — unlike the AP invoice agent. This is asserted by the QA gate.

 Column set verified live against EBS_Vision_12214 PDOI tables: BATCH_ID is
 NUMBER (not a string); the agreement total is AMOUNT_AGREED (there is no
 BLANKET_TOTAL_AMOUNT); PO_LINES_INTERFACE has no ATTRIBUTE columns, so per-line
 audit (match status / exceptions) lives in agent_trace.json + the QA report,
 not in the interface — held lines never reach the interface anyway.
================================================================================
"""

from __future__ import annotations

import csv
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

HEADER_COLS = [
    "INTERFACE_HEADER_ID", "BATCH_ID", "ORG_ID", "ACTION", "DOCUMENT_TYPE_CODE",
    "DOCUMENT_SUBTYPE", "PO_HEADER_ID", "VENDOR_ID", "VENDOR_SITE_ID",
    "VENDOR_DOC_NUM", "CURRENCY_CODE", "AGENT_ID", "APPROVAL_STATUS",
    "EFFECTIVE_DATE", "EXPIRATION_DATE", "AMOUNT_AGREED", "AMOUNT_LIMIT",
    "TERMS_ID", "PROCESS_CODE", "ATTRIBUTE1", "ATTRIBUTE2",
]

LINE_COLS = [
    "INTERFACE_LINE_ID", "INTERFACE_HEADER_ID", "ACTION", "LINE_NUM",
    "SHIPMENT_NUM", "LINE_TYPE_ID", "LINE_TYPE", "ITEM", "ITEM_ID",
    "ITEM_DESCRIPTION", "CATEGORY_ID", "CATEGORY", "UNIT_OF_MEASURE", "UOM_CODE",
    "UNIT_PRICE", "QUANTITY", "EFFECTIVE_DATE", "EXPIRATION_DATE",
]

# Interface columns that are Oracle DATE types — the loader binds these as date
# objects, not strings, so binding never depends on the session NLS_DATE_FORMAT.
DATE_COLS = {"EFFECTIVE_DATE", "EXPIRATION_DATE"}


def _d(value: Any) -> Decimal:
    return Decimal(str(value))


def _iso(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, (date, datetime)):
        return value.strftime("%Y-%m-%d")
    return str(value)[:10]


class PDOIInterfaceWriter:
    """Accumulates PDOI interface rows and emits the two CSVs."""

    DEFAULT_LINE_TYPE_ID = 1        # 'Goods' on Vision
    DEFAULT_LINE_TYPE = "Goods"

    def __init__(self,
                 batch_id: int | None = None,
                 org_id: int = 204):
        self.org_id = org_id
        # BATCH_ID is a NUMBER column in PDOI; derive a numeric batch id.
        self.batch_id = batch_id or int(
            datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S"))
        self.headers: list[dict[str, Any]] = []
        self.lines: list[dict[str, Any]] = []
        self._next_header_id = 1
        self._next_line_id = 1

    # ------------------------------------------------------------------
    def add_renewal(self,
                    agreement: dict[str, Any],
                    supplier: dict[str, Any],
                    extracted: dict[str, Any],
                    term: dict[str, Any],
                    coded_lines: list[dict[str, Any]],
                    agent_run_id: str,
                    confidence: float) -> int:
        """Add one renewed agreement (1 header + N catalog lines)."""
        header_id = self._next_header_id
        self._next_header_id += 1

        blanket_total = sum(
            (_d(cl["extended_amount"]) for cl in coded_lines), Decimal("0"))

        header = {
            "INTERFACE_HEADER_ID": header_id,
            "BATCH_ID": self.batch_id,
            "ORG_ID": self.org_id,
            "ACTION": "UPDATE",          # renew existing agreement by PO_HEADER_ID
            "DOCUMENT_TYPE_CODE": "BLANKET",
            "DOCUMENT_SUBTYPE": "BLANKET",
            "PO_HEADER_ID": agreement["po_header_id"],
            "VENDOR_ID": supplier["vendor_id"],
            "VENDOR_SITE_ID": supplier["vendor_site_id"],
            "VENDOR_DOC_NUM": extracted.get("quote_number") or "",
            "CURRENCY_CODE": extracted.get("currency")
                             or agreement.get("currency_code") or "USD",
            "AGENT_ID": agreement.get("agent_id") or "",
            "APPROVAL_STATUS": "INCOMPLETE",   # buyer approves the renewal in EBS
            "EFFECTIVE_DATE": _iso(term.get("new_effective_date")),
            "EXPIRATION_DATE": _iso(term.get("new_expiration_date")),
            "AMOUNT_AGREED": f"{blanket_total:.2f}",
            "AMOUNT_LIMIT": f"{blanket_total:.2f}",
            "TERMS_ID": agreement.get("terms_id") or "",
            "PROCESS_CODE": "PENDING",         # PDOI picks up PENDING rows
            "ATTRIBUTE1": agent_run_id,
            "ATTRIBUTE2": f"{confidence:.3f}",
        }
        self.headers.append(header)

        for cl in coded_lines:
            self.lines.append(self._catalog_line(header_id, cl, term))

        return header_id

    # ------------------------------------------------------------------
    def _catalog_line(self, header_id: int, cl: dict[str, Any],
                      term: dict[str, Any]) -> dict[str, Any]:
        line = {
            "INTERFACE_LINE_ID": self._next_line_id,
            "INTERFACE_HEADER_ID": header_id,
            "ACTION": "UPDATE",
            "LINE_NUM": cl["line_number"],
            "SHIPMENT_NUM": 1,
            "LINE_TYPE_ID": cl.get("line_type_id") or self.DEFAULT_LINE_TYPE_ID,
            "LINE_TYPE": self.DEFAULT_LINE_TYPE,
            "ITEM": cl.get("item_number") or "",
            "ITEM_ID": cl.get("inventory_item_id") or "",
            "ITEM_DESCRIPTION": (cl.get("description") or "")[:240],
            "CATEGORY_ID": cl.get("category_id") or "",
            "CATEGORY": cl.get("category") or "",
            "UNIT_OF_MEASURE": cl.get("uom") or "Each",
            "UOM_CODE": cl.get("uom_code") or "",
            "UNIT_PRICE": f"{_d(cl['new_unit_price']):.2f}",
            "QUANTITY": cl.get("estimated_qty") or "",
            "EFFECTIVE_DATE": _iso(term.get("new_effective_date")),
            "EXPIRATION_DATE": _iso(term.get("new_expiration_date")),
        }
        self._next_line_id += 1
        return line

    # ------------------------------------------------------------------
    def write(self, out_dir: str | Path) -> tuple[Path, Path]:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        hdr_path = out / "PO_HEADERS_INTERFACE.csv"
        ln_path = out / "PO_LINES_INTERFACE.csv"

        with open(hdr_path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=HEADER_COLS)
            w.writeheader()
            w.writerows(self.headers)
        with open(ln_path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=LINE_COLS)
            w.writeheader()
            w.writerows(self.lines)
        return hdr_path, ln_path
