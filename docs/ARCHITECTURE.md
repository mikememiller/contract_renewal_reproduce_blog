<!-- Syntax Corporation © 2026 — EBS Contract Renewal PAF -->
# Architecture

The PAF pattern, one shape: **document → extract → governed EBS tools →
deterministic policy → EBS Open Interface**, with a QA gate + branded deliverables.

## Components (`src/ebs_contract_renewal_paf/`)
| Module | Responsibility |
|--------|----------------|
| `config.py` | settings precedence (flag > JSON > env > default); no hard-coded secrets |
| `db.py` | python-oracledb **thick/NNE** connection (dev/test + reference engine) |
| `repository.py` | `EBSRepository` protocol + Live + Mock; bind-var, org-scoped SQL |
| `extractor.py` | Deterministic pipe-delimited parser (zero deps) + optional LLM; factory |
| `policy_engine.py` | escalation dual-tolerance + term assessment — deterministic, outside the LLM |
| `interface_writer.py` | builds the **balanced** PDOI batch (header `AMOUNT_AGREED` = Σ line price×qty) |
| `qa_checks.py` | pre-load validation gate → `PASS/HOLD/FAIL` + `loadable` |
| `interface_loader.py` | optional, gated, batch-cleanable INSERT into PDOI (off by default) |
| `renewal_agent.py` | orchestrator; `process()` + `process_extracted()` (PAF split) |
| `mcp_ebs_server.py` | local/stdio reference MCP (production uses the managed MCP) |
| `cli.py` | `python -m ebs_contract_renewal_paf` entry point |

## Production vs reference
- **Production runtime:** PAF (ADB 26ai sidecar) → **OCI Database Tools Managed
  MCP** (HTTPS + OAuth/IAM) → EBS 19c **PL/SQL** (`XXPAF_RENEWAL_PKG`). The load
  runs as the standard **Import Price Catalogs** program. See `PAF_INTEGRATION.md`.
- **Reference/test:** the Python engine above — also the **test oracle** that the
  EBS PL/SQL must match (parity test on the golden record).

## Key design choices
- DI of repository + extractor → identical pipeline on mock (hermetic) or live
  EBS by swapping one constructor arg.
- Deterministic policy/QA kept out of the LLM → auditable, reproducible.
- Extraction degrades gracefully (deterministic default) → runs with only the DB.
- Read-only by default; the renewal **load is off the MCP path**.
- Output must **balance**; QA gate before anything leaves the agent.
- The renewed agreement stages as **INCOMPLETE** → a human buyer approves it; the
  agent never auto-approves a contract.

## Renewal-specific notes (verified live, EBS_Vision_12214)
- Renewal references the **existing agreement by `PO_HEADER_ID`** with
  `ACTION='UPDATE'` — `DOCUMENT_NUM` is an obsoleted online-patch stub here.
- `BATCH_ID` is **NUMBER**; the header total column is **`AMOUNT_AGREED`** (there
  is no `BLANKET_TOTAL_AMOUNT` on the interface); `PO_LINES_INTERFACE` has **no
  ATTRIBUTE columns** (per-line audit lives in the trace/QA report).
- `UOM_CODE` for 'Each' is **`Ea`** (not 'EA').
- Tax is **not** applied at the agreement level → no TAX line (unlike AP).
