<!-- Syntax Corporation © 2026 — EBS Contract Renewal PAF -->
# EBS Contract Renewal PAF — Blanket Purchase Agreement Renewal Agent

A Syntax **Private Agent Factory (PAF)** agent for Oracle E-Business Suite that
turns a supplier **blanket-agreement renewal quote** into a validated, balanced
**Purchasing Documents Open Interface (PDOI)** batch — ready for the standard
**Import Price Catalogs** program. Built and verified live against
**EBS_Vision_12214** (19c).

```
renewal quote → extract → governed EBS reads → deterministic renewal policy
              → balanced PDOI batch → QA gate → (standard import) → renewed BPA
```

## Why it exists
Renewing hundreds of expiring blanket agreements by hand is slow and error-prone:
buyers re-key supplier price lists, miss escalation creep, and let coverage lapse.
This agent reads the existing agreement from EBS, validates the supplier's
proposed prices and term against deterministic policy, and stages a clean PDOI
batch — leaving the **buyer to approve** the renewed agreement in EBS.

## What it does (pipeline)
1. **Extract** the renewal quote (supplier, agreement #, new term, per-line new
   prices + estimated annual quantities). Deterministic parser by default; an
   optional LLM extractor for messy quotes.
2. **Govern the EBS reads** (read-only, bind-variable, org-scoped): existing
   BLANKET agreement + current line prices, supplier site, UOM code, idempotency.
3. **Apply deterministic policy** (outside the LLM, auditable):
   - **Price-escalation dual tolerance** — HOLD a line only when the increase
     breaches **both** a % cap (7%) **and** a material annual-$ floor ($250).
   - **Term** — contiguity with the expiring term, length ≤ 36 months.
   - **Validity** — item still active/orderable, supplier site active.
4. **Build a balanced PDOI batch** — `PO_HEADERS_INTERFACE` /
   `PO_LINES_INTERFACE`, `ACTION='UPDATE'` referencing the existing
   `PO_HEADER_ID`, `APPROVAL_STATUS='INCOMPLETE'` (buyer approves in EBS).
   Header `AMOUNT_AGREED` = Σ(line price × qty).
5. **QA gate** → `PASS / HOLD / FAIL` + `loadable`. Nothing loads unless clean.

## Quickstart (mock, hermetic)
```bash
./setup.sh
source .venv/bin/activate
ebs-renewal-paf sample_data/renewal_acme_facilities.txt --backend mock
```

## Live run (EBS Vision)
```bash
export EBS_PASSWORD=...          # never hard-coded
ebs-renewal-paf sample_data/renewal_hvac_4467.txt --backend live --config conn.json
```
Outputs `output/PO_HEADERS_INTERFACE.csv`, `output/PO_LINES_INTERFACE.csv`,
`agent_trace.json`, `qa_report.json`. Add `--load-to-ebs --yes` to stage rows
directly (off by default; loadable batches only).

## Golden record
**BPA 4467** — *HVAC Express* (vendor 1717), 5 HVAC facilities lines, term
01-JAN-04 → 31-DEC-10. The sample renewal proposes 2011–2013 with a +10% increase
on the heat-pump thermostat (line 4) → that line **HOLDs**; the rest auto-approve;
the batch balances to **$17,920.00**.

## Tests
```bash
pytest -m "not live"                              # 43 hermetic tests
EBS_RUN_LIVE=1 EBS_PASSWORD=... pytest -m live    # live golden + PDOI round-trip
```

## Layout
- `src/ebs_contract_renewal_paf/` — the engine (config, db, repository,
  extractor, policy_engine, interface_writer, qa_checks, renewal_agent,
  interface_loader, mcp_ebs_server, cli).
- `ebs/` — the production `XXPAF_RENEWAL_PKG` PL/SQL + parity harness + managed-MCP
  tool definitions.
- `docs/` — architecture, interface contract, security, operations, PAF integration.
- `deliverables/` — Syntax-branded sales/design/SOW/BOM/ROI generators.
- `QA_REPORT.md` — the QA gate result + honesty register.

© 2026 Syntax Corporation · Confidential
