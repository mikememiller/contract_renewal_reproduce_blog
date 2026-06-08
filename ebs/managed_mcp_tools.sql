--------------------------------------------------------------------------------
-- Syntax Corporation (c) 2026 - All Rights Reserved
-- Project : EBS Contract Renewal PAF - BPA Renewal Automation Agent
-- Module  : managed_mcp_tools.sql - OCI Database Tools Managed MCP definitions
-- Version : 1.0.0   Build : 2026.06.04   Date : 2026-06-04
--------------------------------------------------------------------------------
-- Publishes the renewal agent's governed reads + policy as named MCP tools and
-- SQL Reports on the OCI Database Tools Managed MCP, so the PAF LLM NEVER writes
-- free-form SQL. Bind the Database Tools Connection to a least-privilege EBS user
-- (SELECT on the listed objects + EXECUTE on XXPAF.XXPAF_RENEWAL_PKG). Writes
-- stay OFF the MCP path: the PDOI load runs as the standard "Import Price
-- Catalogs" program (or a governed XXPAF job) - see docs/PAF_INTEGRATION.md.
--
-- This file is the registration contract; in the OCI console you create each as
-- a "SQL Report" (parameterized SELECT) or "Custom Tool" (PL/SQL) with the names
-- below. The SQL mirrors LiveEBSRepository exactly (verified vs EBS_Vision_12214).
--------------------------------------------------------------------------------

-- =============================== SQL REPORTS ================================
-- Tool: get_agreement_header  (params: :agreement_num, :org_id)
SELECT ph.segment1 AS agreement_num, ph.po_header_id, ph.type_lookup_code,
       ph.authorization_status, ph.org_id, ph.vendor_id, ph.vendor_site_id,
       ph.currency_code, ph.agent_id, ph.terms_id, ph.start_date, ph.end_date,
       ph.blanket_total_amount, ph.amount_limit
  FROM apps.po_headers_all ph
 WHERE ph.segment1 = :agreement_num
   AND ph.org_id = :org_id
   AND ph.type_lookup_code = 'BLANKET';

-- Tool: get_agreement_lines  (params: :po_header_id, :org_id)
SELECT pl.line_num, pl.po_line_id, pl.item_id AS inventory_item_id,
       msi.segment1 AS item_number, pl.item_description AS description,
       pl.unit_meas_lookup_code AS uom, pl.unit_price AS current_unit_price,
       pl.line_type_id, pl.category_id,
       (SELECT mc.segment1||'.'||mc.segment2 FROM apps.mtl_categories_b mc
         WHERE mc.category_id = pl.category_id) AS category,
       CASE WHEN msi.inventory_item_id IS NULL THEN 'N'
            WHEN NVL(msi.enabled_flag,'Y')='Y'
                 AND NVL(msi.purchasing_enabled_flag,'Y')='Y' THEN 'Y'
            ELSE 'N' END AS item_active
  FROM apps.po_lines_all pl
  LEFT JOIN apps.mtl_system_items_b msi
    ON msi.inventory_item_id = pl.item_id AND msi.organization_id = :org_id
 WHERE pl.po_header_id = :po_header_id
 ORDER BY pl.line_num;

-- Tool: get_supplier_site  (params: :vendor_id, :org_id)
SELECT * FROM (
  SELECT s.vendor_id, s.segment1 AS vendor_num, s.vendor_name,
         s.num_1099 AS tax_id, ss.vendor_site_id, ss.vendor_site_code,
         ss.payment_method_lookup_code AS payment_method,
         ss.purchasing_site_flag, ss.inactive_date AS site_inactive_date,
         s.terms_id, t.name AS payment_terms
    FROM apps.ap_suppliers s
    JOIN apps.ap_supplier_sites_all ss
         ON ss.vendor_id = s.vendor_id AND ss.org_id = :org_id
    LEFT JOIN apps.ap_terms t ON t.term_id = s.terms_id
   WHERE s.vendor_id = :vendor_id
   ORDER BY NVL2(ss.purchasing_site_flag, 0, 1), ss.vendor_site_id
) WHERE ROWNUM = 1;

-- Tool: resolve_uom_code  (params: :unit_of_measure)
SELECT uom_code FROM apps.mtl_units_of_measure
 WHERE UPPER(unit_of_measure) = UPPER(:unit_of_measure);

-- Tool: get_latest_item_price  (params: :item_id, :org_id)
-- The blog's "pull latest unit prices from the EBS database" step: the most
-- recent priced PO line for the item (current market reality vs the agreement).
SELECT * FROM (
  SELECT pl.unit_price AS latest_price, ph.segment1 AS source_po,
         ph.creation_date AS source_date
    FROM apps.po_lines_all pl
    JOIN apps.po_headers_all ph
         ON ph.po_header_id = pl.po_header_id AND ph.org_id = :org_id
   WHERE pl.item_id = :item_id AND pl.unit_price IS NOT NULL
   ORDER BY ph.creation_date DESC, pl.po_line_id DESC
) WHERE ROWNUM = 1;

-- ============================ CUSTOM PL/SQL TOOLS ==========================
-- Tool: check_renewal_exists  -> XXPAF.XXPAF_RENEWAL_PKG.renewal_exists
--   returns 'Y'/'N' for (:vendor_id, :org_id, :new_effective_date)
-- Tool: evaluate_renewal_line -> XXPAF.XXPAF_RENEWAL_PKG.evaluate_line
--   returns status/escalation_pct/dollar_impact/reason for one line
-- Tool: evaluate_renewal_term -> XXPAF.XXPAF_RENEWAL_PKG.evaluate_term
--   returns ';'-delimited term exception codes
--
-- Example custom-tool wrapper returning JSON (register the SELECT as a tool):
SELECT JSON_OBJECT(
         'status'         VALUE st,
         'escalation_pct' VALUE pct,
         'dollar_impact'  VALUE imp,
         'reason'         VALUE rs
       ) AS result
  FROM (
    SELECT st, pct, imp, rs FROM (
      SELECT NULL st, NULL pct, NULL imp, NULL rs FROM dual
    )
  );
-- (In OCI, implement evaluate_renewal_line as a PL/SQL custom tool that calls
--  XXPAF_RENEWAL_PKG.evaluate_line and returns the JSON above. The inline SELECT
--  here is only a shape placeholder for the registration UI.)

-- ============================ LEAST-PRIVILEGE GRANTS ========================
-- Run as APPS (or the EBS DBA) for the dedicated MCP read user XXPAF_MCP_RO:
--   GRANT SELECT ON apps.po_headers_all          TO XXPAF_MCP_RO;
--   GRANT SELECT ON apps.po_lines_all            TO XXPAF_MCP_RO;
--   GRANT SELECT ON apps.mtl_system_items_b      TO XXPAF_MCP_RO;
--   GRANT SELECT ON apps.mtl_categories_b        TO XXPAF_MCP_RO;
--   GRANT SELECT ON apps.ap_suppliers            TO XXPAF_MCP_RO;
--   GRANT SELECT ON apps.ap_supplier_sites_all   TO XXPAF_MCP_RO;
--   GRANT SELECT ON apps.ap_terms                TO XXPAF_MCP_RO;
--   GRANT SELECT ON apps.mtl_units_of_measure    TO XXPAF_MCP_RO;
--   GRANT EXECUTE ON XXPAF.XXPAF_RENEWAL_PKG     TO XXPAF_MCP_RO;
-- No INSERT/UPDATE/DELETE grants: the renewal LOAD is off the MCP path.
