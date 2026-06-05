"""
================================================================================
 Syntax Corporation © 2026 — All Rights Reserved
--------------------------------------------------------------------------------
 Project : EBS Contract Renewal PAF — BPA Renewal Automation Agent
 Module  : deliverables/pricing.py — the ONE pricing model
 Version : 1.0.0      Build : 2026.06.04      Date : 2026-06-04
--------------------------------------------------------------------------------
 Computes a single pricing + ROI model from the spec inputs and emits
 dist/pricing.json. Every customer-facing deliverable (sales deck, SOW, ROI
 calculator, BOM) reads THIS output, so all figures match across documents.
================================================================================
"""

from __future__ import annotations

import json
from pathlib import Path

# --- inputs (mirror spec.yaml) ----------------------------------------------
RATE_CARD = {"onshore": 175, "nearshore": 85, "offshore": 65}
DELIVERY_MIX = {"onshore": 0.2, "nearshore": 0.4, "offshore": 0.4}
TIMELINE_WEEKS = 8
HOURS_PER_WEEK = 80               # blended ~2-person vertical-slice team
RUN_HOURS_PER_MONTH = 40
AGENT_LICENSE_PER_YEAR = 35_000
MS_TERMS = [12, 24, 36]
TERM_DISCOUNT_PCT = {12: 0, 24: 10, 36: 20}

# OCI consumption (License Included; BYOL ~ -72%)
ADB_MONTHLY_BASE = 600.0          # ADB 26ai sidecar (ECPU + storage), small
PER_RENEWAL_OCI = 0.10            # OCR pages + LLM tokens + ECPU/storage per txn
VOLUME_TIERS = [1000, 4000, 20000]
BYOL_FACTOR = 0.28                # BYOL is ~72% lower than License Included

# ROI inputs
ANNUAL_VOLUME = 4000
CURRENT_COST_PER_TXN = 180.0      # manual: buyer re-key + price research + rework
AUTOMATED_COST_PER_TXN = 12.0     # straight-through cost (OCI + light oversight)
TARGET_STP_PCT = 75              # share fully automated; rest get agent-assist
ASSISTED_COST_PER_TXN = 70.0      # exceptions still much faster than manual
AVG_AGREEMENT_VALUE = 180.0       # informational ($ per agreement-year, k-scale handled in UI)


def _round(x: float, n: int = 2) -> float:
    return round(x, n)


def blended_rate() -> float:
    return sum(RATE_CARD[k] * DELIVERY_MIX[k] for k in RATE_CARD)


def implementation() -> dict:
    hrs = TIMELINE_WEEKS * HOURS_PER_WEEK
    rate = blended_rate()
    fee = hrs * rate
    return {"timeline_weeks": TIMELINE_WEEKS, "hours": hrs,
            "blended_rate": _round(rate), "fixed_fee": _round(fee)}


def oci_monthly(volume_per_year: int, byol: bool = False) -> float:
    variable = (volume_per_year / 12.0) * PER_RENEWAL_OCI
    base = ADB_MONTHLY_BASE * (BYOL_FACTOR if byol else 1.0)
    return base + variable


def managed_services() -> dict:
    rate = blended_rate()
    run_team = RUN_HOURS_PER_MONTH * rate
    license_m = AGENT_LICENSE_PER_YEAR / 12.0
    oci_m = oci_monthly(ANNUAL_VOLUME)
    base_monthly = run_team + license_m + oci_m
    terms = {}
    for t in MS_TERMS:
        disc = TERM_DISCOUNT_PCT[t] / 100.0
        monthly = base_monthly * (1 - disc)
        terms[str(t)] = {
            "monthly": _round(monthly),
            "annual": _round(monthly * 12),
            "total_term": _round(monthly * t),
            "discount_pct": TERM_DISCOUNT_PCT[t],
        }
    return {"run_team_monthly": _round(run_team),
            "license_monthly": _round(license_m),
            "oci_monthly": _round(oci_m),
            "base_monthly": _round(base_monthly),
            "terms": terms}


def oci_bom() -> dict:
    rows = []
    for v in VOLUME_TIERS:
        li = oci_monthly(v, byol=False)
        byol = oci_monthly(v, byol=True)
        rows.append({"volume_per_year": v,
                     "license_included_monthly": _round(li),
                     "license_included_annual": _round(li * 12),
                     "byol_monthly": _round(byol),
                     "byol_annual": _round(byol * 12)})
    return {"tiers": rows}


def roi() -> dict:
    vol = ANNUAL_VOLUME
    stp = TARGET_STP_PCT / 100.0
    auto = vol * stp
    assisted = vol * (1 - stp)
    current_annual = vol * CURRENT_COST_PER_TXN
    future_annual = auto * AUTOMATED_COST_PER_TXN + assisted * ASSISTED_COST_PER_TXN
    annual_savings = current_annual - future_annual
    ms = managed_services()
    impl = implementation()
    year1_cost = impl["fixed_fee"] + ms["terms"]["12"]["annual"]
    annual_run = ms["terms"]["12"]["annual"]
    payback_months = (impl["fixed_fee"] / ((annual_savings - annual_run) / 12.0)
                      if annual_savings > annual_run else None)
    three_yr_savings = annual_savings * 3
    three_yr_cost = impl["fixed_fee"] + annual_run * 3
    three_yr_net = three_yr_savings - three_yr_cost
    return {
        "annual_volume": vol,
        "current_cost_per_txn": CURRENT_COST_PER_TXN,
        "automated_cost_per_txn": AUTOMATED_COST_PER_TXN,
        "assisted_cost_per_txn": ASSISTED_COST_PER_TXN,
        "target_stp_pct": TARGET_STP_PCT,
        "current_annual_cost": _round(current_annual),
        "future_annual_cost": _round(future_annual),
        "annual_savings": _round(annual_savings),
        "annual_run_cost": _round(annual_run),
        "year1_total_cost": _round(year1_cost),
        "payback_months": _round(payback_months, 1) if payback_months else None,
        "three_year_net_savings": _round(three_yr_net),
        "three_year_roi_pct": _round(three_yr_net / three_yr_cost * 100, 1),
    }


def model() -> dict:
    return {
        "currency": "USD",
        "rate_card": RATE_CARD,
        "delivery_mix": DELIVERY_MIX,
        "blended_rate": _round(blended_rate()),
        "implementation": implementation(),
        "managed_services": managed_services(),
        "oci_bom": oci_bom(),
        "roi": roi(),
    }


if __name__ == "__main__":
    out = Path(__file__).resolve().parent / "dist" / "pricing.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    m = model()
    out.write_text(json.dumps(m, indent=2))
    print(f"wrote {out}")
    print(f"  blended rate     : ${m['blended_rate']}/hr")
    print(f"  implementation   : ${m['implementation']['fixed_fee']:,.0f} "
          f"({m['implementation']['hours']} hrs)")
    for t in ("12", "24", "36"):
        mt = m["managed_services"]["terms"][t]
        print(f"  managed svc {t}mo : ${mt['monthly']:,.2f}/mo "
              f"(−{mt['discount_pct']}%)")
    r = m["roi"]
    print(f"  annual savings   : ${r['annual_savings']:,.0f}")
    print(f"  payback          : {r['payback_months']} months")
    print(f"  3-yr ROI         : {r['three_year_roi_pct']}%")
