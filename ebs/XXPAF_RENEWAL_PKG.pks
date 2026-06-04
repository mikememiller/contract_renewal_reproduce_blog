--------------------------------------------------------------------------------
-- Syntax Corporation (c) 2026 - All Rights Reserved
-- Project : EBS Contract Renewal PAF - BPA Renewal Automation Agent
-- Module  : XXPAF_RENEWAL_PKG.pks - package specification
-- Version : 1.0.0   Build : 2026.06.04   Date : 2026-06-04
--------------------------------------------------------------------------------
-- Production-side renewal policy + PDOI staging, deployed in the custom XXPAF
-- schema. This package is the system-of-record home of the business logic; the
-- Python engine (src/ebs_contract_renewal_paf) is its parity test oracle (see
-- tests + docs/PAF_INTEGRATION.md). It is published to the OCI Database Tools
-- Managed MCP as governed custom tools (ebs/managed_mcp_tools.sql).
--
-- Tolerances mirror spec.yaml exactly:
--   g_escalation_pct   = 7.0    (per-line price-increase ceiling)
--   g_escalation_floor = 250.00 (material annual-dollar impact floor)
--   g_max_term_months  = 36
--
-- All reads are read-only; the only writes are INSERTs into the standard
-- PO_HEADERS_INTERFACE / PO_LINES_INTERFACE (PDOI) staging tables.
--------------------------------------------------------------------------------
CREATE OR REPLACE PACKAGE XXPAF.XXPAF_RENEWAL_PKG AS

  g_escalation_pct    CONSTANT NUMBER := 7.0;
  g_escalation_floor  CONSTANT NUMBER := 250.00;
  g_max_term_months   CONSTANT NUMBER := 36;

  -- Per-line escalation verdict, mirroring policy_engine.evaluate_renewal_line.
  --   p_status OUT: 'AUTO' | 'HOLD' | 'ERROR'
  --   p_reason OUT: exception code (e.g. PRICE_ESCALATION_10.00PCT_$700.00) or NULL
  PROCEDURE evaluate_line (
    p_current_price   IN  NUMBER,
    p_new_price       IN  NUMBER,
    p_estimated_qty   IN  NUMBER,
    p_status          OUT VARCHAR2,
    p_escalation_pct  OUT NUMBER,
    p_dollar_impact   OUT NUMBER,
    p_reason          OUT VARCHAR2
  );

  -- Whole months between two dates (mirrors policy_engine._months_between).
  FUNCTION months_between_terms (
    p_start IN DATE,
    p_end   IN DATE
  ) RETURN NUMBER;

  -- Term assessment, mirroring policy_engine.evaluate_term. Returns a
  -- ';'-delimited list of term exception codes ('' when clean).
  FUNCTION evaluate_term (
    p_new_effective   IN DATE,
    p_new_expiration  IN DATE,
    p_prior_expiration IN DATE
  ) RETURN VARCHAR2;

  -- Idempotency: a successor BLANKET agreement already exists for the vendor on
  -- or after the proposed effective date? (mirrors check_renewal_exists)
  FUNCTION renewal_exists (
    p_vendor_id IN NUMBER,
    p_org_id    IN NUMBER,
    p_new_eff   IN DATE
  ) RETURN VARCHAR2;   -- 'Y' | 'N'

END XXPAF_RENEWAL_PKG;
/
