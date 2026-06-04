"""Syntax Corporation © 2026 — EBS Contract Renewal PAF — live EBS tests.

These require a live connection to EBS_Vision_12214 and are opt-in:
    EBS_RUN_LIVE=1 EBS_PASSWORD=... pytest -m live
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from conftest import requires_live  # type: ignore

pytestmark = pytest.mark.live


@pytest.fixture
def live_conn(live_settings):
    from ebs_contract_renewal_paf.db import EBSConnection
    with EBSConnection(live_settings, interactive=False) as conn:
        yield conn


@pytest.fixture
def live_repo(live_conn, live_settings):
    from ebs_contract_renewal_paf.repository import LiveEBSRepository
    return LiveEBSRepository(live_conn, org_id=live_settings.org_id)


@requires_live
def test_dialtone(live_settings):
    from ebs_contract_renewal_paf.db import dialtone
    assert dialtone(live_settings, interactive=False) is True


@requires_live
def test_get_agreement_4467(live_repo):
    ag = live_repo.get_agreement("4467")
    assert ag is not None
    assert ag["po_header_id"] == 33467
    assert ag["vendor_id"] == 1717
    assert ag["type_lookup_code"] == "BLANKET"
    assert ag["authorization_status"] == "APPROVED"
    assert len(ag["lines"]) == 5
    prices = {l["line_num"]: float(l["current_unit_price"]) for l in ag["lines"]}
    assert prices == {1: 16.89, 2: 30.0, 3: 30.0, 4: 350.0, 5: 135.0}
    assert all(l["item_active"] == "Y" for l in ag["lines"])


@requires_live
def test_get_supplier_hvac_express(live_repo):
    s = live_repo.get_supplier(vendor_id=1717)
    assert s and s["vendor_name"] == "HVAC Express"
    assert s["vendor_site_id"] == 4060
    assert s["purchasing_site_flag"] == "Y"
    assert s["site_inactive_date"] is None


@requires_live
def test_resolve_uom_each_is_Ea(live_repo):
    # Verified Phase-1 gotcha: 'Each' -> 'Ea' (not 'EA') on this instance.
    assert live_repo.resolve_uom_code("Each") == "Ea"


@requires_live
def test_check_renewal_exists_false_for_golden(live_repo):
    assert live_repo.check_renewal_exists(1717, "2011-01-01") is False


@requires_live
def test_end_to_end_live_4467(live_conn, live_repo, hvac_quote_text,
                              live_settings):
    from ebs_contract_renewal_paf.extractor import DeterministicExtractor
    from ebs_contract_renewal_paf.renewal_agent import RenewalAgent

    agent = RenewalAgent(live_repo, DeterministicExtractor(),
                         org_id=live_settings.org_id, qa_conn=live_conn)
    trace = agent.process(hvac_quote_text)

    assert trace.supplier_match["vendor_id"] == 1717
    assert trace.agreement_match["po_header_id"] == 33467
    assert not trace.idempotency_block

    # line 4 (heat-pump thermostat 350->385 = +10%, $700 impact) holds; rest auto
    holds = [lr for lr in trace.line_results if not lr["auto_approve"]]
    assert [lr["line_number"] for lr in holds] == [4]
    assert not trace.auto_approved

    # balanced PDOI batch against the real agreement
    hdr = agent.writer.headers[0]
    line_sum = sum(Decimal(l["UNIT_PRICE"]) * Decimal(str(l["QUANTITY"]))
                   for l in agent.writer.lines)
    assert Decimal(hdr["AMOUNT_AGREED"]) == line_sum == Decimal("17920.00")
    assert all(l["UOM_CODE"] == "Ea" for l in agent.writer.lines)

    # QA: HOLD (escalation) but no hard errors; referential checks pass
    rpt = agent.qa_reports[0]
    assert rpt.status == "HOLD", rpt.to_dict()
    assert not rpt.errors


@requires_live
def test_loader_round_trip_inserts_and_purges(live_conn, live_repo,
                                              live_settings):
    """Stage a clean, fully-auto renewal into PDOI, verify it persisted, then
    purge it — leaving the database exactly as it was. Uses a within-tolerance
    quote so the batch is loadable."""
    from ebs_contract_renewal_paf.extractor import DeterministicExtractor
    from ebs_contract_renewal_paf.renewal_agent import RenewalAgent
    from ebs_contract_renewal_paf.interface_loader import load_renewals

    # all lines within 7% / under $250 impact -> fully AUTO -> loadable
    clean_quote = (
        "HVAC Express\n"
        "Quote Number: HVX-RENEW-CLEAN-4467\n"
        "Existing Agreement: 4467\n"
        "Currency: USD\n"
        "Proposed Term Start: 2011-01-01\n"
        "Proposed Term End: 2013-12-31\n"
        "1 | AC Filter | 50 | 17.50\n"
        "2 | Thermostat - Cooling | 10 | 31.00\n"
    )
    agent = RenewalAgent(live_repo, DeterministicExtractor(),
                         org_id=live_settings.org_id, qa_conn=live_conn)
    agent.process(clean_quote)
    assert agent.qa_reports[0].status == "PASS", agent.qa_reports[0].to_dict()
    batch = agent.writer.batch_id

    def counts():
        h = live_conn.query_one(
            "SELECT COUNT(*) n FROM apps.po_headers_interface WHERE batch_id=:b",
            {"b": batch})["n"]
        ids = ",".join(str(x["INTERFACE_HEADER_ID"]) for x in agent.writer.headers)
        l = live_conn.query_one(
            f"SELECT COUNT(*) n FROM apps.po_lines_interface "
            f"WHERE interface_header_id IN ({ids})")["n"]
        return h, l

    assert counts() == (0, 0)
    try:
        res = load_renewals(live_conn, agent.writer.headers, agent.writer.lines,
                            agent.qa_reports, confirm=True)
        assert res == {"headers": 1, "lines": 2, "skipped": 0}
        assert counts() == (1, 2)
    finally:
        ids = ",".join(str(x["INTERFACE_HEADER_ID"]) for x in agent.writer.headers)
        with live_conn._cursor() as cur:
            cur.execute(f"DELETE FROM apps.po_lines_interface "
                        f"WHERE interface_header_id IN ({ids})")
            cur.execute("DELETE FROM apps.po_headers_interface "
                        "WHERE batch_id=:b", {"b": batch})
            live_conn.connection.commit()
    assert counts() == (0, 0)


@requires_live
def test_loader_skips_non_loadable(live_conn, live_repo, hvac_quote_text,
                                   live_settings):
    """A held (over-escalated) renewal must never reach the interface tables."""
    from ebs_contract_renewal_paf.extractor import DeterministicExtractor
    from ebs_contract_renewal_paf.renewal_agent import RenewalAgent
    from ebs_contract_renewal_paf.interface_loader import load_renewals

    agent = RenewalAgent(live_repo, DeterministicExtractor(),
                         org_id=live_settings.org_id, qa_conn=live_conn)
    agent.process(hvac_quote_text)   # line 4 holds
    assert agent.qa_reports[0].status == "HOLD"
    res = load_renewals(live_conn, agent.writer.headers, agent.writer.lines,
                        agent.qa_reports, confirm=True)
    assert res["headers"] == 0 and res["skipped"] == 1
