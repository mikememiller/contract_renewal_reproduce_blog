"""
================================================================================
 Syntax Corporation © 2026 — All Rights Reserved
--------------------------------------------------------------------------------
 Project : EBS Contract Renewal PAF — BPA Renewal Automation Agent
 Module  : renewal_agent.py — orchestrator
 Version : 1.0.0      Build : 2026.06.04      Date : 2026-06-04
--------------------------------------------------------------------------------
 Mirrors the PAF flow, with the repository and extractor injected so the same
 orchestrator runs against mock fixtures or the live EBS database:

   1. extract               -> renewal quote header + proposed lines
   2. EBS lookups (repo)    -> supplier, existing agreement, idempotency, UOM
   3. policy                -> per-line escalation + term assessment
   4. build + QA            -> PDOI interface rows + qa_report
================================================================================
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from .extractor import RenewalExtractor
from .interface_writer import PDOIInterfaceWriter
from .policy_engine import evaluate_renewal_line, evaluate_term
from .qa_checks import QAReport, validate_renewal
from .repository import EBSRepository


@dataclass
class AgentTrace:
    """Explainability log — required for auditable procurement automation."""

    run_id: str
    agreement_num: str | None = None
    extracted: dict[str, Any] | None = None
    supplier_match: dict[str, Any] | None = None
    agreement_match: dict[str, Any] | None = None
    term: dict[str, Any] | None = None
    line_results: list[dict[str, Any]] = field(default_factory=list)
    idempotency_block: bool = False
    auto_approved: bool = False
    exceptions: list[str] = field(default_factory=list)
    confidence: float = 0.0
    qa: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "agreement_num": self.agreement_num,
            "extracted": self.extracted,
            "supplier_match": self.supplier_match,
            "agreement_match": ({k: v for k, v in self.agreement_match.items()
                                 if k != "lines"}
                                if self.agreement_match else None),
            "term": _jsonable(self.term) if self.term else None,
            "line_results": self.line_results,
            "idempotency_block": self.idempotency_block,
            "auto_approved": self.auto_approved,
            "exceptions": self.exceptions,
            "confidence": self.confidence,
            "qa": self.qa,
        }


class RenewalAgent:
    """Processes renewal quotes using an injected repository + extractor."""

    def __init__(self,
                 repository: EBSRepository,
                 extractor: RenewalExtractor,
                 org_id: int = 204,
                 qa_conn: Any | None = None):
        self.repo = repository
        self.extractor = extractor
        self.org_id = org_id
        self.qa_conn = qa_conn  # optional EBSConnection for referential QA
        self.writer = PDOIInterfaceWriter(org_id=org_id)
        self.qa_reports: list[QAReport] = []
        self._uom_cache: dict[str, str | None] = {}

    # ------------------------------------------------------------------
    def process(self, quote_text: str) -> AgentTrace:
        """Full pipeline: extract the quote text, then process it."""
        extracted = self.extractor.extract(quote_text)
        return self.process_extracted(extracted)

    def process_extracted(self, extracted: dict[str, Any]) -> AgentTrace:
        """Process an already-extracted renewal quote dict (steps 2-4).

        Split out from process() so a PAF flow can perform extraction in its own
        LLM node and hand the structured quote to a single policy/QA tool.
        """
        run_id = f"REN-{uuid.uuid4().hex[:10].upper()}"
        trace = AgentTrace(run_id=run_id)
        trace.extracted = extracted
        trace.agreement_num = extracted.get("agreement_num")

        # supplier lookup
        supplier = self.repo.get_supplier(
            vendor_name=extracted.get("vendor_name"),
            tax_id=extracted.get("vendor_tax_id"),
        )
        if supplier is None:
            trace.exceptions.append("SUPPLIER_NOT_FOUND")
            return trace
        trace.supplier_match = supplier

        # existing agreement lookup
        agreement = self.repo.get_agreement(extracted["agreement_num"])
        if agreement is None:
            trace.exceptions.append(
                f"AGREEMENT_NOT_FOUND_{extracted['agreement_num']}")
            return trace
        trace.agreement_match = agreement

        # term assessment
        term = evaluate_term(extracted, agreement)
        trace.term = term

        # idempotency: has this renewal already been created?
        if term.get("new_effective_date") is not None:
            if self.repo.check_renewal_exists(
                    supplier["vendor_id"],
                    term["new_effective_date"].strftime("%Y-%m-%d")):
                trace.idempotency_block = True
                trace.exceptions.append("RENEWAL_ALREADY_EXISTS")
                return trace

        # line-by-line escalation + coding
        coded_lines: list[dict[str, Any]] = []
        all_auto = True
        for line in extracted["lines"]:
            res = evaluate_renewal_line(line, agreement)
            trace.line_results.append({
                "line_number": res.line_number,
                "matched": res.matched,
                "auto_approve": res.auto_approve,
                "exceptions": res.exceptions,
                "current_unit_price": _s(res.current_unit_price),
                "new_unit_price": _s(res.new_unit_price),
                "escalation_pct": _s(res.escalation_pct),
                "dollar_impact": _s(res.dollar_impact),
            })
            if not res.auto_approve:
                all_auto = False

            ag_line = next((l for l in agreement["lines"]
                            if l["line_num"] == line.get("agreement_line_num")),
                           None)
            if ag_line is None:
                ag_line = next((l for l in agreement["lines"]
                                if l.get("item_number") == line.get("item_number")),
                               {})

            uom = ag_line.get("uom") or "Each"
            coded_lines.append({
                "line_number": res.line_number,
                "item_number": ag_line.get("item_number"),
                "inventory_item_id": ag_line.get("inventory_item_id"),
                "description": ag_line.get("description"),
                "uom": uom,
                "uom_code": self._uom_code(uom),
                "category_id": ag_line.get("category_id"),
                "category": ag_line.get("category"),
                "line_type_id": ag_line.get("line_type_id"),
                "item_active": ag_line.get("item_active"),
                "new_unit_price": line["new_unit_price"],
                "estimated_qty": line.get("estimated_qty"),
                "extended_amount": float(
                    (res.extended_amount if res.extended_amount is not None
                     else Decimal("0"))),
                "match_status": "AUTO" if res.auto_approve else "HOLD",
                "exceptions": res.exceptions,
            })

        trace.auto_approved = all_auto and not term.get("exceptions")
        trace.confidence = self._confidence(extracted, coded_lines, term)

        # build interface rows
        header_id = self.writer.add_renewal(
            agreement=agreement, supplier=supplier, extracted=extracted,
            term=term, coded_lines=coded_lines, agent_run_id=run_id,
            confidence=trace.confidence,
        )

        # QA gate over the just-built rows for this renewal
        header = next(h for h in self.writer.headers
                      if h["INTERFACE_HEADER_ID"] == header_id)
        ren_lines = [l for l in self.writer.lines
                     if l["INTERFACE_HEADER_ID"] == header_id]
        report = validate_renewal(header, ren_lines, extracted, coded_lines,
                                  term, agreement=agreement, supplier=supplier,
                                  conn=self.qa_conn, org_id=self.org_id)
        self.qa_reports.append(report)
        trace.qa = report.to_dict()
        return trace

    # ------------------------------------------------------------------
    def _uom_code(self, uom: str) -> str | None:
        if uom not in self._uom_cache:
            try:
                self._uom_cache[uom] = self.repo.resolve_uom_code(uom)
            except Exception:
                self._uom_cache[uom] = None
        return self._uom_cache[uom]

    @staticmethod
    def _confidence(extracted: dict[str, Any],
                    coded: list[dict[str, Any]],
                    term: dict[str, Any]) -> float:
        if not coded:
            return 0.0
        clean = sum(1 for c in coded if c.get("match_status") == "AUTO")
        line_score = clean / len(coded)
        term_score = 0.0 if term.get("exceptions") else 1.0
        return round((line_score * 0.8) + (term_score * 0.2), 3)

    # ------------------------------------------------------------------
    def flush(self, out_dir):
        return self.writer.write(out_dir)


def _s(value: Any) -> str | None:
    return str(value) if value is not None else None


def _jsonable(d: dict[str, Any]) -> dict[str, Any]:
    return {k: (v.strftime("%Y-%m-%d") if hasattr(v, "strftime") else v)
            for k, v in d.items()}
