"""Syntax Corporation © 2026 — EBS Contract Renewal PAF — mock e2e agent tests."""
from __future__ import annotations

from decimal import Decimal

from ebs_contract_renewal_paf.extractor import DeterministicExtractor
from ebs_contract_renewal_paf.renewal_agent import RenewalAgent


def test_mock_repo_agreement_and_supplier(mock_repo):
    ag = mock_repo.get_agreement("BPA-90001")
    assert ag and len(ag["lines"]) == 3
    s = mock_repo.get_supplier(vendor_name="acme facilities")
    assert s and s["vendor_id"] == 90042
    assert mock_repo.resolve_uom_code("Each") == "Ea"
    assert mock_repo.get_supplier(vendor_name="No Such Co") is None


def test_end_to_end_acme_mock(mock_repo, acme_quote_text):
    agent = RenewalAgent(mock_repo, DeterministicExtractor(), org_id=204)
    trace = agent.process(acme_quote_text)

    assert trace.supplier_match["vendor_id"] == 90042
    assert trace.agreement_match["po_header_id"] == 990001
    assert not trace.idempotency_block

    # line 2 (BELT-B 50->60 = +20%, impact 800) must HOLD; others auto
    holds = [lr for lr in trace.line_results if not lr["auto_approve"]]
    assert [lr["line_number"] for lr in holds] == [2]
    assert not trace.auto_approved

    # PDOI rows balance: header blanket total == sum(line price*qty)
    hdr = agent.writer.headers[0]
    line_sum = sum(Decimal(l["UNIT_PRICE"]) * Decimal(str(l["QUANTITY"]))
                   for l in agent.writer.lines)
    assert Decimal(hdr["AMOUNT_AGREED"]) == line_sum == Decimal("12100.00")

    # term is contiguous + 36 months -> clean
    assert trace.term["term_months"] == 36
    assert trace.term["exceptions"] == []

    # QA: well-formed but on HOLD (escalation), not loadable, no hard errors
    rpt = agent.qa_reports[0]
    assert rpt.status == "HOLD"
    assert not rpt.errors


def test_process_extracted_matches_full_process(mock_repo, acme_quote_text):
    ex = DeterministicExtractor()
    extracted = ex.extract(acme_quote_text)

    a_full = RenewalAgent(mock_repo, ex)
    t_full = a_full.process(acme_quote_text)
    a_split = RenewalAgent(mock_repo, ex)
    t_split = a_split.process_extracted(extracted)

    assert t_full.supplier_match["vendor_id"] == t_split.supplier_match["vendor_id"]
    assert t_full.auto_approved == t_split.auto_approved
    assert a_full.qa_reports[0].status == a_split.qa_reports[0].status
    assert len(a_full.writer.lines) == len(a_split.writer.lines)


def test_supplier_not_found_short_circuits(mock_repo):
    extracted = {"vendor_name": "Nonexistent Vendor", "agreement_num": "BPA-90001",
                 "lines": []}
    agent = RenewalAgent(mock_repo, DeterministicExtractor())
    trace = agent.process_extracted(extracted)
    assert "SUPPLIER_NOT_FOUND" in trace.exceptions
    assert trace.agreement_match is None


def test_agreement_not_found_short_circuits(mock_repo):
    extracted = {"vendor_name": "Acme Facilities", "agreement_num": "NOPE-1",
                 "lines": []}
    agent = RenewalAgent(mock_repo, DeterministicExtractor())
    trace = agent.process_extracted(extracted)
    assert any(e.startswith("AGREEMENT_NOT_FOUND") for e in trace.exceptions)


def test_mcp_tool_functions_json_serializable(mock_repo, acme_quote_text):
    import json
    from ebs_contract_renewal_paf.mcp_ebs_server import (
        run_process_renewal, run_validate_renewal,
    )

    out = run_process_renewal(mock_repo, acme_quote_text)
    json.dumps(out, default=str)
    assert set(out) == {"trace", "interface_headers", "interface_lines", "qa"}
    assert out["trace"]["supplier_match"]["vendor_id"] == 90042
    assert out["qa"][0]["status"] == "HOLD"  # BELT-B escalation

    extracted = DeterministicExtractor().extract(acme_quote_text)
    out2 = run_validate_renewal(mock_repo, extracted)
    json.dumps(out2, default=str)
    assert len(out2["interface_lines"]) == len(out["interface_lines"])


def test_end_to_end_writes_csvs(mock_repo, acme_quote_text, tmp_path):
    agent = RenewalAgent(mock_repo, DeterministicExtractor())
    agent.process(acme_quote_text)
    hdr_csv, ln_csv = agent.flush(tmp_path)
    assert hdr_csv.exists() and ln_csv.exists()
    assert hdr_csv.read_text().count("\n") >= 2  # header + 1 row
