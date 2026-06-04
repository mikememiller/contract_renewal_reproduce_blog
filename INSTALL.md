<!-- Syntax Corporation © 2026 — EBS Contract Renewal PAF -->
# Installation & operation

## Step 1 — Install
```bash
./setup.sh            # creates .venv (--system-site-packages), installs the agent
source .venv/bin/activate
ebs-renewal-paf sample_data/renewal_acme_facilities.txt --backend mock
```
On restricted networks where PyPI is blocked, `setup.sh` falls back to
`--no-deps` and reuses an already-installed `python-oracledb`.

## Step 2 — Oracle Instant Client (live path only)
The EBS Vision DB enforces **Native Network Encryption (NNE)**; `python-oracledb`
**thin** mode fails `DPY-3001`, so the live path needs **thick** mode + the
Instant Client. Default location `~/lib/oracle/instantclient`.
- macOS first run: `xattr -dr com.apple.quarantine ~/lib/oracle/instantclient`
- Override with `EBS_INSTANT_CLIENT_DIR`.

## Step 3 — Connect to EBS
Settings precedence: **flag > JSON (`--config`) > env > default**.
```bash
cp conn.example.json conn.json     # conn.json is gitignored
export EBS_PASSWORD=...             # preferred; never hard-code in conn.json
ebs-renewal-paf sample_data/renewal_hvac_4467.txt --backend live --config conn.json
```
Env vars: `EBS_HOST EBS_PORT EBS_SID EBS_USER EBS_PASSWORD EBS_ORG_ID
EBS_INSTANT_CLIENT_DIR`. Password also accepted via interactive `getpass`.

## Step 4 — Outputs
Into `--out` (default `output/`):
- `PO_HEADERS_INTERFACE.csv`, `PO_LINES_INTERFACE.csv` — the PDOI batch
- `agent_trace.json` — full explainability log (per-line escalation, term, QA)
- `qa_report.json` — the QA gate findings

## Step 5 — Load into EBS
**Recommended (audit-preserving):** hand the CSVs to the standard **Import Price
Catalogs** (PDOI) program via SQL*Loader / OIC; the buyer reviews and approves
the renewed agreement (rows stage as `APPROVAL_STATUS='INCOMPLETE'`).

**Direct staging (optional, gated):**
```bash
ebs-renewal-paf <quote> --backend live --load-to-ebs --yes
```
Only `loadable` (PASS) batches are inserted into the interface tables; HOLD/FAIL
batches are skipped. The loader never touches base PO tables.

## Step 6 — Deploy the production PL/SQL (optional)
```bash
sqlplus apps/<pw>@EBSDB @ebs/XXPAF_RENEWAL_PKG.pks
sqlplus apps/<pw>@EBSDB @ebs/XXPAF_RENEWAL_PKG.pkb
sqlplus apps/<pw>@EBSDB @ebs/XXPAF_RENEWAL_utplsql.sql   # parity check
```
Then register the managed-MCP tools (`ebs/managed_mcp_tools.sql`) and grant the
least-privilege read user. See `docs/PAF_INTEGRATION.md`.

## Exit codes
`0` = no FAIL renewals · `3` = at least one renewal FAILed QA (useful for CI).
