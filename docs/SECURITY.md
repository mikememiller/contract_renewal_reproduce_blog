<!-- Syntax Corporation © 2026 — EBS Contract Renewal PAF -->
# Security

## Secrets
- DB password is **never** hard-coded. Sourced (in order): explicit override →
  `EBS_PASSWORD` env → JSON config (with a warning) → interactive `getpass`.
- `conn.json` and `.env` are **gitignored**. Settings dataclass keeps the
  password out of its repr/logs.

## SQL safety
- **Bind variables only** — no string interpolation in any query (injection-safe
  by construction). Verified across `repository.py`, `qa_checks.py`,
  `interface_loader.py`.
- Every read is **org-scoped** (`org_id` bind). In production the managed-MCP
  service account calls `FND_GLOBAL.APPS_INITIALIZE` per session to set multi-org
  context.
- Lookups use the **APPS public synonyms** (e.g. `apps.po_headers_all`).

## Least privilege (production)
- The OCI Database Tools Connection binds a **read-only** EBS user with `SELECT`
  on the listed objects + `EXECUTE` on `XXPAF.XXPAF_RENEWAL_PKG` only — **no DML
  grants**. See `ebs/managed_mcp_tools.sql`.
- Writes stay **off the MCP path**: the PDOI load runs as the standard import
  program or a governed `XXPAF` job.

## Write controls
- Read-only by default. The optional direct loader (`interface_loader.py`)
  requires explicit `confirm=True` (`--load-to-ebs --yes`), only stages
  `loadable` (PASS) batches, **never** touches base PO tables, and is fully
  batch-id purgeable.
- The renewed agreement stages as `APPROVAL_STATUS='INCOMPLETE'` → a human buyer
  approves it in EBS. The agent never approves a contract.

## Auditability
- `agent_trace.json` is a full per-run, per-line explainability log (escalation %,
  dollar impact, term assessment, QA findings) — supports SOX / procurement audit.
- Deterministic policy (outside the LLM) makes every HOLD reproducible.
