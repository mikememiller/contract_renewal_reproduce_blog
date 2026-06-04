"""
================================================================================
 Syntax Corporation © 2026 — All Rights Reserved
--------------------------------------------------------------------------------
 Project : EBS Contract Renewal PAF — BPA Renewal Automation Agent
 Module  : repository.py — EBS data-access layer (live + mock)
 Version : 1.0.0      Build : 2026.06.04      Date : 2026-06-04
--------------------------------------------------------------------------------
 Defines the EBSRepository protocol the agent depends on, plus two concrete
 implementations:

   * MockEBSRepository  — reads sample_data/*.json (hermetic, offline tests).
   * LiveEBSRepository  — bind-variable SQL against the real EBS Vision DB.
                          Every query is READ-ONLY and org-scoped. The SQL has
                          been verified live against EBS_Vision_12214 using the
                          golden record BPA 4467 (header_id 33467).

 All access is via the APPS schema's public synonyms. In a production PAF
 deployment the service account calls FND_GLOBAL.APPS_INITIALIZE per session to
 set multi-org security context (see docs/SECURITY.md).
================================================================================
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from .db import EBSConnection


@runtime_checkable
class EBSRepository(Protocol):
    """Read-only EBS lookups required by the renewal agent."""

    def get_agreement(
        self, agreement_num: str
    ) -> dict[str, Any] | None: ...

    def get_supplier(
        self,
        vendor_name: str | None = None,
        vendor_num: str | None = None,
        tax_id: str | None = None,
        vendor_id: int | None = None,
    ) -> dict[str, Any] | None: ...

    def resolve_uom_code(self, unit_of_measure: str) -> str | None: ...

    def check_renewal_exists(
        self, vendor_id: int, new_effective_date: str
    ) -> bool: ...


# ===========================================================================
# Mock implementation — JSON fixtures (offline / hermetic tests)
# ===========================================================================

class MockEBSRepository:
    """Serves the same shapes as LiveEBSRepository from sample_data/*.json."""

    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir)

    def _load(self, name: str) -> Any:
        return json.loads((self.data_dir / name).read_text())

    def get_agreement(self, agreement_num):
        for ag in self._load("mock_agreement_master.json"):
            if str(ag["agreement_num"]) == str(agreement_num):
                return ag
        return None

    def get_supplier(self, vendor_name=None, vendor_num=None, tax_id=None,
                     vendor_id=None):
        suppliers = self._load("mock_supplier_master.json")
        # Resolution order: vendor_id > tax_id > vendor_num > exact > fuzzy.
        if vendor_id is not None:
            for s in suppliers:
                if s.get("vendor_id") == vendor_id:
                    return s
        if tax_id:
            for s in suppliers:
                if s.get("tax_id") == tax_id:
                    return s
        if vendor_num:
            for s in suppliers:
                if s.get("vendor_num") == vendor_num:
                    return s
        if vendor_name:
            for s in suppliers:
                if s["vendor_name"].lower() == vendor_name.lower():
                    return s
            for s in suppliers:
                if vendor_name.lower() in s["vendor_name"].lower():
                    return s
        return None

    def resolve_uom_code(self, unit_of_measure):
        uoms = self._load("mock_uom_codes.json")
        for u in uoms:
            if u["unit_of_measure"].lower() == (unit_of_measure or "").lower():
                return u["uom_code"]
        return None

    def check_renewal_exists(self, vendor_id, new_effective_date):
        return False  # the mock master has no successor agreements


# ===========================================================================
# Live implementation — real EBS Vision SQL (read-only, bind variables)
# ===========================================================================

class LiveEBSRepository:
    """Read-only EBS data access against the live Vision database.

    A single EBSConnection is held open for the life of the repository so a
    run reuses one session. All SQL uses bind variables and is org-scoped.
    """

    def __init__(self, conn: EBSConnection, org_id: int = 204):
        self.conn = conn
        self.org_id = org_id

    # ------------------------------------------------------------------
    def get_agreement(self, agreement_num):
        """Fetch a BLANKET purchase agreement header + its current lines.

        Verified live on EBS_Vision_12214 with agreement_num='4467'
        (po_header_id 33467, vendor 1717 HVAC Express, 5 lines).
        """
        header = self.conn.query_one(
            """
            SELECT ph.segment1        AS agreement_num,
                   ph.po_header_id,
                   ph.type_lookup_code,
                   ph.authorization_status,
                   ph.org_id,
                   ph.vendor_id,
                   ph.vendor_site_id,
                   ph.currency_code,
                   ph.agent_id,
                   ph.terms_id,
                   ph.start_date,
                   ph.end_date,
                   ph.blanket_total_amount,
                   ph.amount_limit
              FROM apps.po_headers_all ph
             WHERE ph.segment1 = :agreement_num
               AND ph.org_id = :org_id
               AND ph.type_lookup_code = 'BLANKET'
            """,
            {"agreement_num": str(agreement_num), "org_id": self.org_id},
        )
        if not header:
            return None

        lines = self.conn.query(
            """
            SELECT pl.line_num,
                   pl.po_line_id,
                   pl.item_id            AS inventory_item_id,
                   msi.segment1          AS item_number,
                   pl.item_description   AS description,
                   pl.unit_meas_lookup_code AS uom,
                   pl.unit_price         AS current_unit_price,
                   pl.line_type_id,
                   pl.category_id,
                   (SELECT mc.segment1 || '.' || mc.segment2
                      FROM apps.mtl_categories_b mc
                     WHERE mc.category_id = pl.category_id) AS category,
                   CASE WHEN msi.inventory_item_id IS NULL THEN 'N'
                        WHEN NVL(msi.enabled_flag, 'Y') = 'Y'
                             AND NVL(msi.purchasing_enabled_flag, 'Y') = 'Y'
                        THEN 'Y' ELSE 'N' END AS item_active
              FROM apps.po_lines_all pl
              LEFT JOIN apps.mtl_system_items_b msi
                   ON msi.inventory_item_id = pl.item_id
                  AND msi.organization_id = :org_id
             WHERE pl.po_header_id = :po_header_id
             ORDER BY pl.line_num
            """,
            {"po_header_id": header["po_header_id"], "org_id": self.org_id},
        )
        header["lines"] = lines
        return header

    # ------------------------------------------------------------------
    def get_supplier(self, vendor_name=None, vendor_num=None, tax_id=None,
                     vendor_id=None):
        # NOTE: ROWNUM is applied in an OUTER query AFTER the ORDER BY, otherwise
        # Oracle would pick an arbitrary row and then sort it (a common bug).
        base = """
            SELECT * FROM (
              SELECT s.vendor_id,
                     s.segment1            AS vendor_num,
                     s.vendor_name,
                     s.num_1099            AS tax_id,
                     ss.vendor_site_id,
                     ss.vendor_site_code,
                     ss.payment_method_lookup_code AS payment_method,
                     ss.purchasing_site_flag,
                     ss.inactive_date      AS site_inactive_date,
                     s.terms_id,
                     t.name                AS payment_terms
                FROM apps.ap_suppliers s
                JOIN apps.ap_supplier_sites_all ss
                     ON ss.vendor_id = s.vendor_id AND ss.org_id = :org_id
                LEFT JOIN apps.ap_terms t ON t.term_id = s.terms_id
               WHERE {where}
               ORDER BY NVL2(ss.purchasing_site_flag, 0, 1), ss.vendor_site_id
            ) WHERE ROWNUM = 1
        """
        # Resolution order: vendor_id > tax_id > vendor_num > exact > fuzzy.
        attempts: list[tuple[str, dict[str, Any]]] = []
        if vendor_id is not None:
            attempts.append(("s.vendor_id = :vendor_id",
                             {"org_id": self.org_id, "vendor_id": vendor_id}))
        if tax_id:
            attempts.append(("s.num_1099 = :tax_id",
                             {"org_id": self.org_id, "tax_id": tax_id}))
        if vendor_num:
            attempts.append(("s.segment1 = :vendor_num",
                             {"org_id": self.org_id, "vendor_num": vendor_num}))
        if vendor_name:
            attempts.append(("UPPER(s.vendor_name) = UPPER(:vn)",
                             {"org_id": self.org_id, "vn": vendor_name}))
            attempts.append(("UPPER(s.vendor_name) LIKE UPPER(:vnl)",
                             {"org_id": self.org_id, "vnl": f"%{vendor_name}%"}))
        for where, params in attempts:
            row = self.conn.query_one(base.format(where=where), params)
            if row:
                return row
        return None

    # ------------------------------------------------------------------
    def resolve_uom_code(self, unit_of_measure):
        """Resolve the 3-char UOM_CODE PDOI needs from a UOM name.

        Verified: 'Each' -> 'Ea' on this instance (NOT 'EA').
        """
        if not unit_of_measure:
            return None
        row = self.conn.query_one(
            """
            SELECT uom_code
              FROM apps.mtl_units_of_measure
             WHERE UPPER(unit_of_measure) = UPPER(:uom)
            """,
            {"uom": unit_of_measure},
        )
        return row["uom_code"] if row else None

    # ------------------------------------------------------------------
    def check_renewal_exists(self, vendor_id, new_effective_date):
        """Idempotency: has a successor BLANKET agreement already been created
        for this vendor on/after the proposed renewal effective date?

        Verified live: returns 0 for vendor 1717 on/after 2011-01-01.
        """
        from datetime import date, datetime

        eff = new_effective_date
        if isinstance(eff, str):
            eff = datetime.strptime(eff, "%Y-%m-%d").date()
        elif isinstance(eff, datetime):
            eff = eff.date()
        assert isinstance(eff, date)

        row = self.conn.query_one(
            """
            SELECT COUNT(*) AS n
              FROM apps.po_headers_all ph
             WHERE ph.vendor_id = :vendor_id
               AND ph.org_id = :org_id
               AND ph.type_lookup_code = 'BLANKET'
               AND ph.start_date >= :eff
            """,
            {"vendor_id": vendor_id, "org_id": self.org_id, "eff": eff},
        )
        return bool(row and row["n"] > 0)
