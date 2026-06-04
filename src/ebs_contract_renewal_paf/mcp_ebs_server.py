"""
================================================================================
 Syntax Corporation © 2026 — All Rights Reserved
--------------------------------------------------------------------------------
 Project : EBS Contract Renewal PAF — BPA Renewal Automation Agent
 Module  : mcp_ebs_server.py — MCP server exposing read-only EBS lookups
 Version : 1.0.0      Build : 2026.06.04      Date : 2026-06-04
--------------------------------------------------------------------------------
 Reference/self-hosted MCP server exposing the EBSRepository methods and the
 higher-level renewal tools over stdio. In PRODUCTION the agent reaches EBS via
 the OCI Database Tools Managed MCP (custom PL/SQL tools + SQL Reports calling
 the XXPAF package); this module is the dev/test stand-in and the contract that
 the managed-MCP tool definitions mirror (see ebs/managed_mcp_tools.sql).

 The tool *signatures* are stable; the backend is chosen by EBS_BACKEND
 (live | mock). Requires the optional `mcp` package:  pip install ".[mcp]".
================================================================================
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import Settings
from .repository import EBSRepository, LiveEBSRepository, MockEBSRepository

_SAMPLE_DIR = Path(__file__).resolve().parents[2] / "sample_data"


def build_repository(settings: Settings | None = None) -> EBSRepository:
    """Construct the repository backend selected by settings/env."""
    settings = settings or Settings.resolve()
    if settings.backend == "live":
        from .db import EBSConnection
        conn = EBSConnection(settings, interactive=True).__enter__()
        return LiveEBSRepository(conn, org_id=settings.org_id)
    return MockEBSRepository(_SAMPLE_DIR)


# ---------------------------------------------------------------------------
# Tool implementations — module-level so they are importable and testable
# without the optional `mcp` transport package. main() simply wraps these.
# ---------------------------------------------------------------------------

def _agent_for(repo: EBSRepository):
    from .extractor import DeterministicExtractor
    from .renewal_agent import RenewalAgent
    return RenewalAgent(repo, DeterministicExtractor(),
                        org_id=getattr(repo, "org_id", 204))


def _result(agent, trace) -> dict[str, Any]:
    return {
        "trace": trace.to_dict(),
        "interface_headers": agent.writer.headers,
        "interface_lines": agent.writer.lines,
        "qa": [r.to_dict() for r in agent.qa_reports],
    }


def run_validate_renewal(repo: EBSRepository, extracted: dict) -> dict[str, Any]:
    """Escalation + term policy + QA over an already-extracted renewal quote."""
    agent = _agent_for(repo)
    return _result(agent, agent.process_extracted(extracted))


def run_process_renewal(repo: EBSRepository, quote_text: str) -> dict[str, Any]:
    """End-to-end: extract the quote text, then validate/code/QA."""
    agent = _agent_for(repo)
    return _result(agent, agent.process(quote_text))


def main() -> None:  # pragma: no cover - requires mcp + a transport
    from mcp.server.fastmcp import FastMCP

    repo = build_repository()
    mcp = FastMCP("ebs-contract-renewal-server")

    @mcp.tool()
    def get_agreement(agreement_num: str) -> dict | None:
        """Existing BLANKET agreement header + current price lines."""
        return repo.get_agreement(agreement_num)

    @mcp.tool()
    def get_supplier(vendor_name: str | None = None,
                     vendor_num: str | None = None,
                     tax_id: str | None = None,
                     vendor_id: int | None = None) -> dict | None:
        """Look up a supplier (AP_SUPPLIERS / AP_SUPPLIER_SITES_ALL)."""
        return repo.get_supplier(vendor_name, vendor_num, tax_id, vendor_id)

    @mcp.tool()
    def resolve_uom_code(unit_of_measure: str) -> str | None:
        """Resolve the PDOI UOM_CODE for a unit-of-measure name."""
        return repo.resolve_uom_code(unit_of_measure)

    @mcp.tool()
    def check_renewal_exists(vendor_id: int, new_effective_date: str) -> bool:
        """Idempotency: a successor BLANKET agreement already exists?"""
        return repo.check_renewal_exists(vendor_id, new_effective_date)

    # --- higher-level orchestration tools (ideal for a PAF flow) -----------
    @mcp.tool()
    def validate_renewal(extracted: dict) -> dict:
        """Given an already-extracted renewal quote (e.g. from a PAF LLM node),
        run escalation + term policy + the QA gate against live EBS and return
        the agent trace, the PDOI interface rows, and the QA report. Does not
        write any files or rows."""
        return run_validate_renewal(repo, extracted)

    @mcp.tool()
    def process_renewal(quote_text: str) -> dict:
        """End-to-end: extract the renewal quote text, validate/code/QA against
        live EBS, and return the trace + interface rows + QA report."""
        return run_process_renewal(repo, quote_text)

    mcp.run()


if __name__ == "__main__":  # pragma: no cover
    main()
