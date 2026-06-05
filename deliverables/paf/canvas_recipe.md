<!-- Syntax Corporation © 2026 — EBS Contract Renewal PAF -->
# PAF Agent Builder — canvas recipe (build natively, do NOT spec-import)

PAF flow-import rejects tool-using flows, so build the agent on the **Agent
Builder canvas**. Nodes, in order:

1. **Input** — *File Upload* (renewal quote PDF/text) or *Chat*. For scanned
   quotes, add an OCR step (OCI Document Understanding) before the prompt.
2. **Prompt** — extraction instruction; pin the output JSON schema (see
   `mcp_tool_defs.json` → `renewal_quote` shape).
3. **Agent (LLM)** — a **tool-capable** model (`xai.grok-4`, `openai.gpt-5`, or
   `gpt-4o`; *not* Vertex). Attach the **MCP Server node** → the OCI managed MCP.
4. **MCP tool calls** (governed; the LLM never writes SQL):
   `get_agreement_header` → `get_agreement_lines` → `get_supplier_site` →
   `resolve_uom_code` → `check_renewal_exists` → `evaluate_renewal_line` (per
   line) → `evaluate_renewal_term`.
5. **Combine JSON / Calculator** — assemble the PDOI batch; assert
   `AMOUNT_AGREED = Σ(unit_price × quantity)` (balance check).
6. **Condition** — route on QA status:
   - `PASS` → emit the PDOI CSV / stage for **Import Price Catalogs**;
   - `HOLD` → *Email/Chat Output* to the buyer with the escalation/term reasons;
   - `FAIL` → *Email/Chat Output* to the data steward.
7. **Output** — Email/Chat + the published **REST API** (hook for the KPI
   dashboard + exception-review console).

## Register the managed MCP
MCP Servers tab → Add → managed-MCP **URL** + **OAuth** (authorization-code) or
token. Tools auto-discover (default node timeout 45 s). Multiple MCP servers may
attach to one Agent.

## Writes stay off the MCP
The agent reads + scores + QAs via the MCP. The **load** runs as the standard
**Import Price Catalogs** program (or a governed `XXPAF` job). Enable a
DML-capable custom tool only if confirmed at install.

## QA mechanism
Datasets/Prompt Lab tune prompts but are not a scored eval harness — the
repo's **pytest + golden + Python↔PL/SQL parity** tests remain the QA gate.
