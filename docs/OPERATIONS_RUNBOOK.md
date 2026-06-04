<!-- Syntax Corporation © 2026 — EBS Contract Renewal PAF -->
# Operations runbook

## Daily / batch run
1. Collect supplier renewal quotes (email/portal) → text/PDF into an inbox.
2. Run the agent per quote (mock for dry-runs, live for staging):
   ```bash
   ebs-renewal-paf <quote.txt> --backend live --config conn.json --out output/
   ```
3. Review `qa_report.json`:
   - `PASS` → batch is `loadable`; stage to PDOI and run **Import Price Catalogs**.
   - `HOLD` → buyer review (escalation / term / item status); fix or accept, re-run.
   - `FAIL` → malformed; correct the quote/data and re-run.
4. Buyer approves the renewed agreement in EBS (it stages as `INCOMPLETE`).

## Reading a HOLD
`agent_trace.json.line_results[*]` shows `escalation_pct`, `dollar_impact`, and
the exception code, e.g. `PRICE_ESCALATION_10.00PCT_$700.00`. `term.exceptions`
shows term issues (`COVERAGE_GAP_*`, `TERM_TOO_LONG_*`).

## Tolerances (change control)
Edit `policy_engine.py` constants **and** `XXPAF_RENEWAL_PKG` in lockstep, then
re-run the parity harness (`ebs/XXPAF_RENEWAL_utplsql.sql`). They must stay equal.
Defaults: escalation 7% / $250 floor / 36-month max term.

## PDOI failures
Check `PO_INTERFACE_ERRORS` by `INTERFACE_HEADER_ID`. Common causes: inactive
item, UOM mismatch, supplier site on hold — all pre-screened by the QA gate, so
post-import errors should be rare.

## Idempotency / reruns
Re-running the same quote is safe: the agent blocks if a successor agreement
already exists (`RENEWAL_ALREADY_EXISTS`). The direct loader is batch-id
purgeable for clean retries.

## Monitoring
PAF has no built-in agent monitoring; consume the published REST API into a KPI
dashboard + exception-review console (counts of PASS/HOLD/FAIL, $ escalation
held, agreements renewed). See `PAF_INTEGRATION.md`.

## Backout
Nothing is irreversible pre-approval: purge staged interface rows by `BATCH_ID`;
un-approved `INCOMPLETE` agreements can be cancelled in EBS.
