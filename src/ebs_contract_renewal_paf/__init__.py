"""
================================================================================
 Syntax Corporation © 2026 — All Rights Reserved
--------------------------------------------------------------------------------
 Project : EBS Contract Renewal PAF — BPA Renewal Automation Agent
 Module  : ebs_contract_renewal_paf (package root)
 Version : 1.0.0      Build : 2026.06.04      Date : 2026-06-04
--------------------------------------------------------------------------------
 A Private-Agent-Factory-style agent for Oracle E-Business Suite that ingests a
 supplier blanket-agreement renewal quote, validates the proposed price
 escalation, term, and item/supplier status against live EBS data, and emits a
 balanced Purchasing Documents Open Interface (PDOI) batch for the standard
 "Import Price Catalogs" program (read-only by default).
================================================================================
"""

from __future__ import annotations

__all__ = ["__version__", "__build__", "BANNER"]

__version__ = "1.0.0"
__build__ = "2026.06.04"

BANNER = "Syntax Corporation © 2026 — EBS Contract Renewal PAF v{} (build {})".format(
    __version__, __build__
)
