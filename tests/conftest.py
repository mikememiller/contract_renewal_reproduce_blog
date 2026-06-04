"""Syntax Corporation © 2026 — EBS Contract Renewal PAF — pytest fixtures."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

SAMPLE_DIR = ROOT / "sample_data"


@pytest.fixture
def sample_dir() -> Path:
    return SAMPLE_DIR


@pytest.fixture
def acme_quote_text() -> str:
    return (SAMPLE_DIR / "renewal_acme_facilities.txt").read_text()


@pytest.fixture
def hvac_quote_text() -> str:
    return (SAMPLE_DIR / "renewal_hvac_4467.txt").read_text()


@pytest.fixture
def mock_repo(sample_dir):
    from ebs_contract_renewal_paf.repository import MockEBSRepository
    return MockEBSRepository(sample_dir)


def _live_enabled() -> bool:
    return bool(os.environ.get("EBS_PASSWORD")) and \
        os.environ.get("EBS_RUN_LIVE", "").lower() in ("1", "true", "yes")


@pytest.fixture
def live_settings():
    from ebs_contract_renewal_paf.config import Settings
    return Settings.resolve(overrides={"backend": "live"})


requires_live = pytest.mark.skipif(
    not _live_enabled(),
    reason="live EBS tests need EBS_PASSWORD and EBS_RUN_LIVE=1",
)
