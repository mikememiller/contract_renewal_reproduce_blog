#!/usr/bin/env bash
# =============================================================================
#  Syntax Corporation © 2026 — EBS Contract Renewal PAF
#  setup.sh — one-command install. Creates a venv and installs the agent.
#  Works on machines with internet OR on restricted networks where Oracle's
#  python-oracledb is already installed system-wide.
# =============================================================================
set -euo pipefail
cd "$(dirname "$0")"

echo "==> Creating virtual environment (.venv)"
# --system-site-packages lets us reuse an already-installed python-oracledb
python3 -m venv .venv --system-site-packages
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --quiet --upgrade pip >/dev/null 2>&1 || true

echo "==> Installing ebs-contract-renewal-paf"
if pip install -e . >/tmp/ebs_renewal_paf_install.log 2>&1; then
  echo "    installed with dependencies from PyPI"
else
  echo "    PyPI unavailable - using already-installed python-oracledb (--no-deps)"
  pip install -e . --no-deps
fi

echo "==> Verifying"
if python -c "import oracledb" 2>/dev/null; then
  echo "    python-oracledb: OK ($(python -c 'import oracledb;print(oracledb.__version__)'))"
else
  echo "    WARNING: python-oracledb not found. The 'live' backend needs it;"
  echo "             the 'mock' backend works without it."
fi

echo
echo "Done. Next:"
echo "  source .venv/bin/activate"
echo "  ebs-renewal-paf sample_data/renewal_acme_facilities.txt --backend mock"
echo
echo "For the live database, see Step 3 in INSTALL.md."
