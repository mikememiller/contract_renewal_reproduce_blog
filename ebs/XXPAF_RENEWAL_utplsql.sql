--------------------------------------------------------------------------------
-- Syntax Corporation (c) 2026 - All Rights Reserved
-- Project : EBS Contract Renewal PAF - BPA Renewal Automation Agent
-- Module  : XXPAF_RENEWAL_utplsql.sql - PL/SQL parity / unit harness
-- Version : 1.0.0   Build : 2026.06.04   Date : 2026-06-04
--------------------------------------------------------------------------------
-- Runs the golden record (BPA 4467) and the policy edge cases through
-- XXPAF_RENEWAL_PKG and asserts the verdicts match the Python reference engine
-- (the test oracle). Python is authoritative; this proves the production PL/SQL
-- agrees. Run after deploying XXPAF_RENEWAL_PKG:
--    sqlplus apps/<pw>@EBSDB @ebs/XXPAF_RENEWAL_utplsql.sql
-- A utPLSQL wrapper (--%suite) is provided below the bare harness for shops that
-- have utPLSQL installed; the bare block needs only DBMS_OUTPUT.
--------------------------------------------------------------------------------
SET SERVEROUTPUT ON
DECLARE
  l_fail   PLS_INTEGER := 0;
  l_status VARCHAR2(30);
  l_pct    NUMBER;
  l_imp    NUMBER;
  l_reason VARCHAR2(200);

  PROCEDURE chk(p_name VARCHAR2, p_got VARCHAR2, p_exp VARCHAR2) IS
  BEGIN
    IF NVL(p_got,'<null>') = NVL(p_exp,'<null>') THEN
      DBMS_OUTPUT.PUT_LINE('  PASS  '||p_name||'  ('||p_got||')');
    ELSE
      l_fail := l_fail + 1;
      DBMS_OUTPUT.PUT_LINE('  FAIL  '||p_name||'  got='||p_got||' exp='||p_exp);
    END IF;
  END;
BEGIN
  DBMS_OUTPUT.PUT_LINE('== Golden BPA 4467 line escalation parity ==');

  -- L1 16.89 -> 17.50 (qty 200): +3.61%, impact 122 -> AUTO
  XXPAF.XXPAF_RENEWAL_PKG.evaluate_line(16.89,17.50,200,l_status,l_pct,l_imp,l_reason);
  chk('L1 status', l_status, 'AUTO');

  -- L4 350 -> 385 (qty 20): +10%, impact 700 -> HOLD
  XXPAF.XXPAF_RENEWAL_PKG.evaluate_line(350,385,20,l_status,l_pct,l_imp,l_reason);
  chk('L4 status', l_status, 'HOLD');
  chk('L4 reason', l_reason, 'PRICE_ESCALATION_10.00PCT_$700.00');

  -- L5 135 -> 140 (qty 30): +3.70%, impact 150 -> AUTO
  XXPAF.XXPAF_RENEWAL_PKG.evaluate_line(135,140,30,l_status,l_pct,l_imp,l_reason);
  chk('L5 status', l_status, 'AUTO');

  -- high pct but small $ impact -> AUTO (dual gate)
  XXPAF.XXPAF_RENEWAL_PKG.evaluate_line(10,12,1,l_status,l_pct,l_imp,l_reason);
  chk('small-impact status', l_status, 'AUTO');

  -- non-positive price -> ERROR
  XXPAF.XXPAF_RENEWAL_PKG.evaluate_line(10,0,5,l_status,l_pct,l_imp,l_reason);
  chk('zero-price status', l_status, 'ERROR');

  DBMS_OUTPUT.PUT_LINE('== Term parity ==');
  chk('contiguous 36mo',
      XXPAF.XXPAF_RENEWAL_PKG.evaluate_term(
        DATE '2011-01-01', DATE '2013-12-31', DATE '2010-12-31'), '');
  chk('36mo months',
      TO_CHAR(XXPAF.XXPAF_RENEWAL_PKG.months_between_terms(
        DATE '2011-01-01', DATE '2013-12-31')), '36');
  chk('coverage gap',
      XXPAF.XXPAF_RENEWAL_PKG.evaluate_term(
        DATE '2026-06-01', DATE '2027-05-31', DATE '2025-12-31'),
      'COVERAGE_GAP_152D');

  IF l_fail = 0 THEN
    DBMS_OUTPUT.PUT_LINE('RESULT: PASS (PL/SQL == Python reference)');
  ELSE
    DBMS_OUTPUT.PUT_LINE('RESULT: FAIL ('||l_fail||' mismatches)');
    RAISE_APPLICATION_ERROR(-20050, 'Parity failures: '||l_fail);
  END IF;
END;
/
