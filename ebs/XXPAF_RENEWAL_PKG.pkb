--------------------------------------------------------------------------------
-- Syntax Corporation (c) 2026 - All Rights Reserved
-- Project : EBS Contract Renewal PAF - BPA Renewal Automation Agent
-- Module  : XXPAF_RENEWAL_PKG.pkb - package body
-- Version : 1.0.0   Build : 2026.06.04   Date : 2026-06-04
--------------------------------------------------------------------------------
-- Deterministic renewal policy, kept at PARITY with the Python reference engine
-- (policy_engine.py). The parity test (ebs/XXPAF_RENEWAL_utplsql.sql + the
-- Python golden) asserts identical verdicts on the golden record BPA 4467.
--------------------------------------------------------------------------------
CREATE OR REPLACE PACKAGE BODY XXPAF.XXPAF_RENEWAL_PKG AS

  --------------------------------------------------------------------------
  PROCEDURE evaluate_line (
    p_current_price   IN  NUMBER,
    p_new_price       IN  NUMBER,
    p_estimated_qty   IN  NUMBER,
    p_status          OUT VARCHAR2,
    p_escalation_pct  OUT NUMBER,
    p_dollar_impact   OUT NUMBER,
    p_reason          OUT VARCHAR2
  ) IS
    l_qty NUMBER := NVL(p_estimated_qty, 0);
  BEGIN
    p_status         := 'AUTO';
    p_reason         := NULL;
    p_escalation_pct := NULL;
    p_dollar_impact  := NULL;

    -- structural validity
    IF p_new_price IS NULL OR p_new_price <= 0 THEN
      p_status := 'ERROR';
      p_reason := 'NON_POSITIVE_PRICE';
      RETURN;
    END IF;

    IF p_current_price IS NULL OR p_current_price <= 0 THEN
      p_status := 'HOLD';
      p_reason := 'NO_BASELINE_PRICE';
      RETURN;
    END IF;

    -- price-escalation dual tolerance
    p_escalation_pct := (p_new_price - p_current_price) / p_current_price * 100;
    IF p_escalation_pct > 0 THEN
      p_dollar_impact := (p_new_price - p_current_price) * l_qty;
      IF p_escalation_pct > g_escalation_pct
         AND p_dollar_impact > g_escalation_floor THEN
        p_status := 'HOLD';
        p_reason := 'PRICE_ESCALATION_'
                    || TO_CHAR(p_escalation_pct, 'FM990.00') || 'PCT_$'
                    || TO_CHAR(p_dollar_impact, 'FM999990.00');
      END IF;
    END IF;
  END evaluate_line;

  --------------------------------------------------------------------------
  FUNCTION months_between_terms (
    p_start IN DATE,
    p_end   IN DATE
  ) RETURN NUMBER IS
    l_months NUMBER;
  BEGIN
    l_months := (EXTRACT(YEAR FROM p_end) - EXTRACT(YEAR FROM p_start)) * 12
                + (EXTRACT(MONTH FROM p_end) - EXTRACT(MONTH FROM p_start));
    IF EXTRACT(DAY FROM p_end) >= EXTRACT(DAY FROM p_start) - 1 THEN
      l_months := l_months + 1;
    END IF;
    RETURN l_months;
  END months_between_terms;

  --------------------------------------------------------------------------
  FUNCTION evaluate_term (
    p_new_effective    IN DATE,
    p_new_expiration   IN DATE,
    p_prior_expiration IN DATE
  ) RETURN VARCHAR2 IS
    l_exc    VARCHAR2(4000) := '';
    l_months NUMBER;
    l_gap    NUMBER;

    PROCEDURE add_exc(p IN VARCHAR2) IS
    BEGIN
      l_exc := l_exc || CASE WHEN l_exc IS NULL OR l_exc = '' THEN '' ELSE ';' END || p;
    END;
  BEGIN
    IF p_new_effective IS NULL OR p_new_expiration IS NULL THEN
      RETURN 'MISSING_TERM_DATES';
    END IF;

    IF p_new_expiration <= p_new_effective THEN
      add_exc('TERM_END_NOT_AFTER_START');
    END IF;

    l_months := months_between_terms(p_new_effective, p_new_expiration);
    IF l_months > g_max_term_months THEN
      add_exc('TERM_TOO_LONG_' || TO_CHAR(l_months) || 'M');
    END IF;

    IF p_prior_expiration IS NOT NULL THEN
      l_gap := TRUNC(p_new_effective) - TRUNC(p_prior_expiration);
      IF l_gap > 1 THEN
        add_exc('COVERAGE_GAP_' || TO_CHAR(l_gap) || 'D');
      ELSIF l_gap < 1 THEN
        add_exc('TERM_OVERLAP_' || TO_CHAR(1 - l_gap) || 'D');
      END IF;
    END IF;

    RETURN l_exc;
  END evaluate_term;

  --------------------------------------------------------------------------
  FUNCTION renewal_exists (
    p_vendor_id IN NUMBER,
    p_org_id    IN NUMBER,
    p_new_eff   IN DATE
  ) RETURN VARCHAR2 IS
    l_n NUMBER;
  BEGIN
    SELECT COUNT(*)
      INTO l_n
      FROM apps.po_headers_all ph
     WHERE ph.vendor_id = p_vendor_id
       AND ph.org_id = p_org_id
       AND ph.type_lookup_code = 'BLANKET'
       AND ph.start_date >= p_new_eff;
    RETURN CASE WHEN l_n > 0 THEN 'Y' ELSE 'N' END;
  END renewal_exists;

END XXPAF_RENEWAL_PKG;
/
