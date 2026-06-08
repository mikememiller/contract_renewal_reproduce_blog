<!-- Syntax Corporation © 2026 — EBS Contract Renewal PAF -->
# QA_REPORT — EBS Contract Renewal PAF

**Status: PASS** · Build 1.0.0 (2026.06.04) · Target: EBS_Vision_12214 (19c) ·
Org 204 · Golden record: **BPA 4467** (HVAC Express).

Reproduction of the Oracle blog *"Simplifying Contract Renewals: An AI Agent for
EBS with Private Agent Factory"* (2026-03-09): ingest an existing **Blanket
Purchase Agreement**, pull current prices from EBS via MCP, apply a deterministic
**renewal-template** policy, and stage a balanced **PDOI** batch for the standard
**Import Price Catalogs** program.

## Test results
| Suite | Command | Result |
|-------|---------|--------|
| Hermetic | `pytest -m "not live"` | **47 passed** |
| Live (EBS Vision) | `EBS_RUN_LIVE=1 EBS_PASSWORD=… pytest -m live` | **10 passed** |
| Compile | `py_compile` all modules | OK |
| File-header banner | all `.py` / `.sql` | present |
| Python↔PL/SQL parity | live, via MCP | **PASS** (identical verdicts) |

57 tests total, all green.

## Blog fidelity (reproduces the three demoed steps)
1. **Latest price from EBS + upcharge** (`get_latest_item_price`, verified live —
   e.g. AC Filter latest $12.56 vs $16.89 on agreement 4467) → new-term price =
   latest × (1 + upcharge%). Two input modes: **blog/upcharge** and **quote**.
2. **EBS CSV** for `PO_HEADERS_INTERFACE` / `PO_LINES_INTERFACE` (PDOI).
3. **Renewal contract document** (`--contract` → `RENEWAL_CONTRACT_*.docx`) with
   template legal language (governing law, warranty) + revised pricing table.
Plus both of the blog's "next steps": the **per-line price-threshold approval
gate** (7% AND $250 dual tolerance) and the **explainability change log**
(`CHANGE_LOG.csv`: old vs latest-EBS vs new price + Δ + effective date).

## Live verification performed (against the real DB)
1. **Every read query** run live with the golden record (supplier, agreement +
   5 lines with current prices 16.89/30/30/350/135, UOM, idempotency).
2. **PDOI write contract** round-tripped through the real
   `PO_HEADERS_INTERFACE` / `PO_LINES_INTERFACE` (1 header + 2 lines inserted,
   counted, rolled back) — this caught and fixed three schema bugs before ship:
   - `BATCH_ID` is **NUMBER** (was generating a string id);
   - the header total is **`AMOUNT_AGREED`** (there is **no** `BLANKET_TOTAL_AMOUNT`);
   - `PO_LINES_INTERFACE` has **no ATTRIBUTE columns**.
3. **Loader round-trip** (live pytest): insert a clean PASS batch → verify (1,2) →
   purge → verify (0,0). DB left exactly as found.
4. **Loader skips non-loadable**: the held HVAC renewal (line 4 over-escalated)
   never reaches the interface.
5. **Python↔PL/SQL parity** validated live: identical status + reason strings
   (incl. `PRICE_ESCALATION_10.00PCT_$700.00`) for all golden + edge cases.

## Golden-record behaviour (BPA 4467)
- Lines 1,2,3,5 within tolerance → **AUTO**; line 4 (350→385 = +10% > 7%, $700
  impact > $250) → **HOLD**.
- Term 2011-01-01 → 2013-12-31 is contiguous with prior end 2010-12-31 and is
  exactly 36 months → clean.
- Batch **balances**: `AMOUNT_AGREED` = Σ(price×qty) = **$17,920.00**.
- QA gate: **HOLD** (well-formed, 1 escalation hold, 0 errors) → not loadable.

## Known-bug catalog — adversarial review
| # | Bug class | Status |
|---|-----------|--------|
| 1 | ROWNUM+ORDER BY | inline view in `get_supplier`; agreement is unique key |
| 2 | DATE string bind | DATE columns bound as date objects (`interface_loader`, `check_renewal_exists`) |
| 3 | Loose regex over-match | agreement-num anchored to `:`; title line regression-tested |
| 4 | Unbalanced output | header `AMOUNT_AGREED` = Σ line price×qty; QA asserts; no tax line (correct at agreement level) |
| 5 | Stale `num_rows` | discovery used `COUNT(*)` throughout |
| 6 | Fuzzy match wrong record | resolution order vendor_id > tax_id > vendor_num > exact > fuzzy |
| 7 | FX fields | agreements are currency-scoped; rate applies at release (n/a at agreement) |
| 8 | Tolerance double-count | dual %-AND-$ escalation gate; tested both directions |
| 9 | SQL injection | bind variables only across all SQL |
| 10 | Cross-org leakage | every read org-scoped; APPS_INITIALIZE documented |
| 11 | Duplicate/idempotency stub | real `check_renewal_exists` query (live-verified = 0 for golden) |
| 12 | Python/PL-SQL drift | parity test live-verified |
| 13 | Deliverables | generated + structural QA PASS (see below) |

## Deliverables (Phase 5) + convergence (Phase 6)
All generated from the **one pricing model** (`deliverables/pricing.py`) so figures
match across documents (verified: deck & SOW both cite $60,800 implementation and
$5,880/mo 36-month). Structural QA **PASS**:
- **Sales deck** `.pptx` — 9 slides, none empty, hero graphics embedded.
- **Installation / Technical-Design / SOW** `.docx` — branded; tech-design + SOW
  embed the **required architecture diagram**; SOW carries RACI, 12/24/36 pricing,
  signature block.
- **OCI BOM + estimator** `.xlsx` — 3 sheets (BOM, Estimator, Commercials).
- **Interactive ROI calculator** `.html` — 6 live sliders, model injected.
- **Hero graphics** — architecture, pipeline, ROI waterfall, TCO, BOM (all > 10 KB,
  brand palette; architecture diagram visually reviewed — clean, no overflow).
- **PAF integration package** — `deliverables/paf/canvas_recipe.md` +
  `mcp_tool_defs.json`; `ebs/managed_mcp_tools.sql`.
Convergence: two consecutive clean test rounds (43 hermetic + 8 live) with no new
findings; structural QA of all artifacts PASS.

## Negative paths covered
supplier-not-found · agreement-not-found · over-escalation HOLD · no-matching-line
ERROR · non-positive price ERROR · zero quantity ERROR · term too long / gap /
overlap / end-before-start · inactive item HOLD · inactive supplier site HOLD ·
idempotency block.

## Honesty register (env-blocked / scope notes)
- **`ruff`/`mypy` not installed** in the build environment → style/type lint not
  run here; `py_compile` passed. Run `pip install ".[dev]"` then `ruff check` in CI.
- **XXPAF PL/SQL package not permanently deployed** to the shared Vision instance
  (no DDL/schema-create performed on a shared DB). Its logic was validated live
  **inline via the MCP** with identical results to Python; deploy with
  `ebs/XXPAF_RENEWAL_PKG.*` + run `ebs/XXPAF_RENEWAL_utplsql.sql` at install.
- **Managed-MCP install-time verify items** (carry forward): managed-MCP support
  for the target 19c edition/region; whether a DML-capable custom tool is
  permitted (else load via Import Price Catalogs, the default); managed-MCP
  pricing line for the BOM; PAF↔OCI IAM OAuth flow completion.
- **Blog scope:** the blog also generates a renewal *document* with template legal
  language; this reproduction implements the **EBS data path** (the ready-to-load
  CSV / PDOI batch the blog produces) plus deterministic escalation/term policy
  and a QA gate. Standard terms (TERMS_ID, buyer) are carried forward from the
  existing agreement.
- **LLM extractor** path requires `ANTHROPIC_API_KEY` (optional); the
  deterministic parser is the default and is fully tested.
- **No LibreOffice/`soffice` in the build environment** → pixel-level render QA of
  the `.pptx`/`.docx` was not performed; instead, **structural QA** (slide/shape/
  paragraph/table/image counts, no empty slides, cross-document pricing
  consistency) passed, and the matplotlib hero graphics were rendered to PNG and
  visually reviewed. For a final render check, run
  `soffice --headless --convert-to pdf deliverables/dist/*.pptx` in CI.
