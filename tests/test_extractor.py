"""Syntax Corporation © 2026 — EBS Contract Renewal PAF — extractor tests."""
from __future__ import annotations

import pytest

from ebs_contract_renewal_paf.extractor import (
    DeterministicExtractor,
    ExtractionError,
    make_extractor,
)


def test_parses_acme_quote(acme_quote_text):
    out = DeterministicExtractor().extract(acme_quote_text)
    assert out["quote_number"] == "AFS-RENEW-2026-0001"
    assert out["quote_date"] == "2025-11-15"
    assert out["agreement_num"] == "BPA-90001"
    assert out["currency"] == "USD"
    assert out["vendor_tax_id"] == "04-1112223"
    assert out["vendor_name"].lower().startswith("acme facilities")
    assert out["new_effective_date"] == "2026-01-01"
    assert out["new_expiration_date"] == "2028-12-31"
    assert len(out["lines"]) == 3
    assert out["lines"][1]["item_number"] == "BELT-B"
    assert out["lines"][1]["estimated_qty"] == 80
    assert out["lines"][1]["new_unit_price"] == 60.0
    # proposed annual value rollup
    assert out["proposed_total"] == pytest.approx(12100.0)


def test_parses_hvac_quote_multiword_items(hvac_quote_text):
    out = DeterministicExtractor().extract(hvac_quote_text)
    assert out["agreement_num"] == "4467"
    assert len(out["lines"]) == 5
    # multi-word item names must survive the pipe-delimited parse
    assert out["lines"][3]["item_number"] == "Thermostat - Heat Pump"
    assert out["lines"][3]["new_unit_price"] == 385.0
    assert [l["agreement_line_num"] for l in out["lines"]] == [1, 2, 3, 4, 5]
    assert out["proposed_total"] == pytest.approx(17920.0)


def test_missing_agreement_number_raises():
    text = (
        "Some Supplier\n"
        "Quote Number: Q-1\n"
        "Proposed Term Start: 2026-01-01\n"
        "Proposed Term End: 2026-12-31\n"
        "1 | A | 10 | 5.00\n"
    )
    with pytest.raises(ExtractionError):
        DeterministicExtractor().extract(text)


def test_missing_lines_raises():
    text = (
        "Some Supplier\n"
        "Quote Number: Q-1\n"
        "Existing Agreement: 4467\n"
        "Proposed Term Start: 2026-01-01\n"
        "Proposed Term End: 2026-12-31\n"
    )
    with pytest.raises(ExtractionError):
        DeterministicExtractor().extract(text)


def test_title_line_not_misread_as_agreement():
    # "Blanket Purchase Agreement — Renewal Quote" (no colon) must NOT be parsed
    # as the agreement number; the real "Existing Agreement: 4467" line wins.
    text = (
        "HVAC Express\n"
        "Blanket Purchase Agreement — Renewal Quote\n"
        "Quote Number: Q-9\n"
        "Existing Agreement: 4467\n"
        "Proposed Term Start: 2026-01-01\n"
        "Proposed Term End: 2026-12-31\n"
        "1 | AC Filter | 10 | 5.00\n"
    )
    out = DeterministicExtractor().extract(text)
    assert out["agreement_num"] == "4467"


def test_factory_default_is_deterministic():
    assert isinstance(make_extractor("deterministic"), DeterministicExtractor)


def test_factory_auto_without_key_falls_back(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert isinstance(make_extractor("auto"), DeterministicExtractor)
