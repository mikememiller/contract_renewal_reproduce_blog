<!-- Syntax Corporation © 2026 — EBS Contract Renewal PAF -->
# PAF integration (OCI managed MCP)

## Topology
```
PAF (ADB 26ai sidecar)  →[HTTPS + OAuth2/IAM]→  OCI Database Tools Managed MCP
   →[Database Tools Connection, private endpoint]→  EBS 19c  (XXPAF PL/SQL + reads)
PDOI load: standard "Import Price Catalogs" program  (OFF the MCP path)
```
The ADB sidecar holds **no EBS data** and is **not in the data path**.

## Managed-MCP setup
1. Create a **Database Tools Connection** to EBS 19c (wallet/secret in OCI Vault,
   private endpoint into the VCN). Bind a **least-privilege read user**
   (`SELECT` on the read objects + `EXECUTE` on `XXPAF_RENEWAL_PKG`; no DML).
2. Publish governed tools from `ebs/managed_mcp_tools.sql`:
   - **SQL Reports:** `get_agreement_header`, `get_agreement_lines`,
     `get_supplier_site`, `resolve_uom_code`.
   - **Custom PL/SQL tools:** `evaluate_renewal_line`, `evaluate_renewal_term`,
     `check_renewal_exists` (wrap `XXPAF_RENEWAL_PKG`, return JSON).
   The LLM **never authors SQL**.
3. In PAF: **MCP Servers → Add** the managed-MCP URL + OAuth (authorization-code)
   or token; tools auto-discover (default node timeout 45 s).

## Agent Builder canvas (build natively — do NOT spec-import)
PAF flow-import rejects tool-using flows, so build on the canvas:
```
File Upload / Chat (renewal quote)
  → Prompt (extraction)  → LLM node (tool-capable: xai.grok-4 / openai.gpt-5 / gpt-4o)
  → MCP Server node (managed MCP: get_agreement_*, get_supplier_site, evaluate_*)
  → Combine JSON → Calculator (balance check)
  → Condition (route on QA status: PASS / HOLD / FAIL)
  → Email/Chat Output (buyer for HOLD; stage PDOI for PASS)
```
Test in **Playground**; **Publish** → the agent exposes a **REST API** (the hook
for the KPI dashboard + exception console).

## Writes stay off the MCP
The agent reads + scores + QAs via the MCP; the **load** runs as the standard
Import Price Catalogs program (or a governed `XXPAF` job). Only enable a
DML-capable custom tool if confirmed at install (a verify item).

## Parity (QA mechanism)
PAF Datasets/Prompt Lab tune prompts but are not a scored eval harness — our
**pytest + golden + Python↔PL/SQL parity** tests remain the QA gate. Keep
`policy_engine.py` and `XXPAF_RENEWAL_PKG` equal; re-run the parity harness on any
tolerance change.

## Install-time verify items
- managed-MCP supports the target EBS 19c (region/edition);
- whether a DML-capable custom tool is permitted (else load via import);
- managed-MCP pricing line for the BOM;
- PAF ↔ OCI IAM OAuth flow completes to the managed-MCP endpoint.
