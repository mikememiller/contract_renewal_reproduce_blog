"""
================================================================================
 Syntax Corporation © 2026 — All Rights Reserved
--------------------------------------------------------------------------------
 Project : EBS Contract Renewal PAF — BPA Renewal Automation Agent
 Module  : interface_loader.py — OPTIONAL direct INSERT into PDOI interface
 Version : 1.0.0      Build : 2026.06.04      Date : 2026-06-04
--------------------------------------------------------------------------------
 OFF BY DEFAULT. The faithful, audit-preserving path is to emit CSVs and let the
 standard "Import Price Catalogs" (PDOI) concurrent program load them. This
 module is a convenience for environments that want the agent to stage rows
 directly into PO_HEADERS_INTERFACE / PO_LINES_INTERFACE.

 Guard rails:
   * never touches the base PO tables (PO_HEADERS_ALL etc.) — interface only;
   * refuses to load a renewal whose QAReport is not loadable;
   * single transaction, explicit commit, bind variables only;
   * empty strings are normalised to NULL so numeric/date columns bind cleanly;
   * DATE columns are bound as date objects (never NLS-format-dependent strings).
================================================================================
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from .db import EBSConnection
from .interface_writer import DATE_COLS, HEADER_COLS, LINE_COLS
from .qa_checks import QAReport


class InterfaceLoadError(RuntimeError):
    pass


def _coerce_date(value: Any) -> Any:
    if value in (None, ""):
        return None
    if isinstance(value, (date, datetime)):
        return value.date() if isinstance(value, datetime) else value
    return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()


def _bindable(row: dict[str, Any], cols: list[str]) -> dict[str, Any]:
    """Build a bind dict: '' -> None (NULL), and DATE columns -> date objects."""
    out: dict[str, Any] = {}
    for c in cols:
        v = row.get(c, None)
        if c in DATE_COLS:
            out[c] = _coerce_date(v)
        else:
            out[c] = None if v == "" else v
    return out


def _insert_sql(table: str, cols: list[str]) -> str:
    collist = ", ".join(cols)
    binds = ", ".join(f":{c}" for c in cols)
    return f"INSERT INTO apps.{table} ({collist}) VALUES ({binds})"


def load_renewals(
    conn: EBSConnection,
    headers: list[dict[str, Any]],
    lines: list[dict[str, Any]],
    qa_reports: list[QAReport],
    *,
    confirm: bool = False,
) -> dict[str, int]:
    """Insert built PDOI rows into the Purchasing interface tables.

    Requires `confirm=True` (the CLI maps this to --load-to-ebs --yes). Only
    renewals whose QAReport.loadable is True are written; their lines follow by
    INTERFACE_HEADER_ID. Returns counts.
    """
    if not confirm:
        raise InterfaceLoadError(
            "Refusing to write to EBS without explicit confirmation "
            "(pass confirm=True / --load-to-ebs --yes)."
        )

    loadable_ids = {
        h["INTERFACE_HEADER_ID"]
        for h, r in zip(headers, qa_reports)
        if r.loadable
    }
    if not loadable_ids:
        return {"headers": 0, "lines": 0, "skipped": len(headers)}

    hdr_sql = _insert_sql("po_headers_interface", HEADER_COLS)
    ln_sql = _insert_sql("po_lines_interface", LINE_COLS)

    inserted_h = inserted_l = 0
    with conn._cursor() as cur:
        for h in headers:
            if h["INTERFACE_HEADER_ID"] in loadable_ids:
                cur.execute(hdr_sql, _bindable(h, HEADER_COLS))
                inserted_h += 1
        for ln in lines:
            if ln["INTERFACE_HEADER_ID"] in loadable_ids:
                cur.execute(ln_sql, _bindable(ln, LINE_COLS))
                inserted_l += 1
        conn.connection.commit()

    return {
        "headers": inserted_h,
        "lines": inserted_l,
        "skipped": len(headers) - len(loadable_ids),
    }
