"""
================================================================================
 Syntax Corporation © 2026 — All Rights Reserved
--------------------------------------------------------------------------------
 Project : EBS Contract Renewal PAF — BPA Renewal Automation Agent
 Module  : deliverables/build_diagrams.py — hero graphics kit (matplotlib)
 Version : 1.0.0      Build : 2026.06.04      Date : 2026-06-04
--------------------------------------------------------------------------------
 Renders the shared high-res visual kit once; every artifact embeds the same
 assets (consistency = polish). Brand palette only; strong contrast; nothing
 overflows its shape. Outputs PNGs into dist/.
   * architecture.png  — REQUIRED technical-architecture / deployment diagram
   * process.png       — renewal pipeline (document → … → PDOI)
   * roi_waterfall.png — current cost → savings → future cost
   * tco.png           — 12/24/36-month managed-services TCO
   * bom.png           — OCI consumption by annual volume tier
================================================================================
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

DIST = Path(__file__).resolve().parent / "dist"
DIST.mkdir(parents=True, exist_ok=True)

NAVY = "#0632A0"; NAVY_DK = "#041F66"; GREEN = "#3CC85A"; CYAN = "#1EB4E6"
GOLD = "#F1D488"; INK = "#16203A"; SLATE = "#5B6577"; PAPER = "#FFFFFF"
MIST = "#F4F7FC"; LINE = "#DCE4F4"

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11})


def _pricing() -> dict:
    return json.loads((DIST / "pricing.json").read_text())


def _box(ax, x, y, w, h, title, lines, fc, tc="white", fs=11):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.06",
                                linewidth=0, facecolor=fc, zorder=2))
    ax.text(x + w / 2, y + h - 0.26, title, ha="center", va="top", color=tc,
            fontsize=fs, fontweight="bold", zorder=3)
    if lines:
        ax.text(x + w / 2, y + h - 0.62, "\n".join(lines), ha="center", va="top",
                color=tc, fontsize=fs - 2.5, zorder=3, linespacing=1.4)


def _arrow(ax, x1, y1, x2, y2, color=NAVY):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>",
                 mutation_scale=16, linewidth=2.2, color=color, zorder=1))


def _tri(ax, x, y, s):
    ax.plot([x, x + s], [y, y], color=GREEN, lw=2.5, zorder=4)
    ax.plot([x, x + s / 2], [y, y + s], color=NAVY, lw=2.5, zorder=4)
    ax.plot([x + s, x + s / 2], [y, y + s], color=CYAN, lw=2.5, zorder=4)


# ---------------------------------------------------------------------------
def architecture():
    fig, ax = plt.subplots(figsize=(12, 6.4), dpi=170)
    ax.set_xlim(0, 12); ax.set_ylim(0, 6.4); ax.axis("off")
    ax.add_patch(plt.Rectangle((0, 0), 12, 6.4, color=PAPER, zorder=0))
    _tri(ax, 0.35, 5.85, 0.32)
    ax.text(0.95, 5.95, "EBS CONTRACT RENEWAL PAF — REFERENCE ARCHITECTURE",
            color=NAVY, fontsize=13, fontweight="bold", va="center")
    ax.text(0.95, 5.6, "Document → extract → governed MCP reads → deterministic policy → PDOI batch → standard import",
            color=SLATE, fontsize=9.5, va="center")

    # PAF sidecar
    _box(ax, 0.4, 3.3, 3.2, 1.7, "PAF · ADB 26ai sidecar",
         ["Agent Builder canvas", "tool-capable LLM (grok-4)",
          "NO EBS data — not in", "the data path"], NAVY)
    # Managed MCP
    _box(ax, 4.4, 3.5, 3.2, 1.3, "OCI Database Tools",
         ["Managed MCP", "HTTPS + OAuth2 / IAM", "governed PL/SQL tools + SQL Reports"], CYAN, tc=INK)
    # EBS
    _box(ax, 8.4, 3.0, 3.2, 2.0, "EBS 19c (OCI)",
         ["System of record · NNE", "XXPAF_RENEWAL_PKG (PL/SQL)",
          "po_headers_all / po_lines_all", "ap_suppliers · mtl_*"], NAVY_DK)
    _arrow(ax, 3.6, 4.15, 4.4, 4.15)
    ax.text(4.0, 4.32, "HTTPS+OAuth", ha="center", color=SLATE, fontsize=7.5)
    _arrow(ax, 7.6, 4.15, 8.4, 4.05)
    ax.text(8.0, 4.32, "DB Tools Conn\n(private endpoint)", ha="center", color=SLATE, fontsize=7)

    # data path bottom: load off MCP
    _box(ax, 0.4, 1.0, 3.2, 1.3, "Renewal quote",
         ["supplier doc / email", "→ LLM extract", "→ structured lines"], GREEN, tc=INK)
    _box(ax, 4.4, 1.0, 3.2, 1.3, "Deterministic policy + QA",
         ["escalation dual-tolerance", "term · item · supplier", "balanced + PASS/HOLD/FAIL"], SLATE)
    _box(ax, 8.4, 1.0, 3.2, 1.3, "PDOI batch → EBS",
         ["PO_HEADERS/LINES_INTERFACE", "Import Price Catalogs", "buyer approves renewal"], NAVY)
    _arrow(ax, 3.6, 1.65, 4.4, 1.65)
    _arrow(ax, 7.6, 1.65, 8.4, 1.65)
    _arrow(ax, 2.0, 3.3, 2.0, 2.3, color=GREEN)
    _arrow(ax, 10.0, 2.3, 10.0, 3.0, color=NAVY)
    ax.text(6.0, 0.55, "Reads via MCP · writes (load) OFF the MCP path (standard import / governed job)",
            ha="center", color=SLATE, fontsize=8.5, style="italic")
    fig.savefig(DIST / "architecture.png", bbox_inches="tight", facecolor=PAPER)
    plt.close(fig)


# ---------------------------------------------------------------------------
def process():
    steps = ["Renewal\nquote", "Extract\n(LLM/parser)", "EBS reads\n(MCP)",
             "Escalation +\nterm policy", "QA gate\nPASS/HOLD/FAIL", "PDOI batch\n→ import"]
    colors = [GREEN, CYAN, NAVY, SLATE, GOLD, NAVY_DK]
    tcs = [INK, INK, "white", "white", INK, "white"]
    fig, ax = plt.subplots(figsize=(12, 2.7), dpi=170)
    ax.set_xlim(0, 12); ax.set_ylim(0, 2.7); ax.axis("off")
    ax.add_patch(plt.Rectangle((0, 0), 12, 2.7, color=PAPER, zorder=0))
    _tri(ax, 0.3, 2.25, 0.26)
    ax.text(0.85, 2.35, "THE RENEWAL PIPELINE", color=NAVY, fontsize=12, fontweight="bold", va="center")
    n = len(steps); w = 1.62; gap = (12 - 0.6 - n * w) / (n - 1); x = 0.3
    for i, (s, c, tc) in enumerate(zip(steps, colors, tcs)):
        _box(ax, x, 0.55, w, 1.2, "", [], c, tc=tc)
        ax.text(x + w / 2, 1.15, s, ha="center", va="center", color=tc, fontsize=9.5, fontweight="bold")
        if i < n - 1:
            _arrow(ax, x + w, 1.15, x + w + gap, 1.15)
        x += w + gap
    fig.savefig(DIST / "process.png", bbox_inches="tight", facecolor=PAPER)
    plt.close(fig)


# ---------------------------------------------------------------------------
def roi_waterfall():
    r = _pricing()["roi"]
    cur = r["current_annual_cost"]; fut = r["future_annual_cost"]; sav = r["annual_savings"]
    fig, ax = plt.subplots(figsize=(7.2, 4.6), dpi=170)
    ax.bar(0, cur, color=SLATE, width=0.6)
    ax.bar(1, sav, bottom=fut, color=GREEN, width=0.6)
    ax.bar(2, fut, color=NAVY, width=0.6)
    for xi, (lab, val, base) in enumerate([("Current\nmanual cost", cur, 0),
                                           ("Annual\nsavings", sav, fut),
                                           ("Future\nrun cost", fut, 0)]):
        ax.text(xi, base + val + cur * 0.02, f"${val:,.0f}", ha="center",
                color=INK, fontsize=10, fontweight="bold")
    ax.set_xticks([0, 1, 2]); ax.set_xticklabels(["Current", "Savings", "Future"])
    ax.set_title("Annual contract-renewal cost — current vs automated",
                 color=NAVY, fontsize=12, fontweight="bold")
    ax.set_ylabel("USD / year", color=SLATE)
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_facecolor(PAPER)
    fig.savefig(DIST / "roi_waterfall.png", bbox_inches="tight", facecolor=PAPER)
    plt.close(fig)


# ---------------------------------------------------------------------------
def tco():
    ms = _pricing()["managed_services"]["terms"]
    terms = ["12", "24", "36"]
    monthly = [ms[t]["monthly"] for t in terms]
    fig, ax = plt.subplots(figsize=(7.2, 4.6), dpi=170)
    bars = ax.bar(range(3), monthly, color=[CYAN, NAVY, NAVY_DK], width=0.55)
    for b, t in zip(bars, terms):
        ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 60,
                f"${b.get_height():,.0f}/mo", ha="center", color=INK,
                fontsize=10, fontweight="bold")
        ax.text(b.get_x() + b.get_width() / 2, b.get_height() / 2,
                f"−{ms[t]['discount_pct']}%", ha="center", color="white",
                fontsize=11, fontweight="bold")
    ax.set_xticks(range(3)); ax.set_xticklabels([f"{t}-month" for t in terms])
    ax.set_title("Managed-services TCO by term", color=NAVY, fontsize=12, fontweight="bold")
    ax.set_ylabel("USD / month", color=SLATE)
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_facecolor(PAPER)
    fig.savefig(DIST / "tco.png", bbox_inches="tight", facecolor=PAPER)
    plt.close(fig)


# ---------------------------------------------------------------------------
def bom():
    tiers = _pricing()["oci_bom"]["tiers"]
    vols = [f"{t['volume_per_year']:,}/yr" for t in tiers]
    li = [t["license_included_annual"] for t in tiers]
    by = [t["byol_annual"] for t in tiers]
    x = range(len(tiers)); w = 0.38
    fig, ax = plt.subplots(figsize=(7.6, 4.6), dpi=170)
    ax.bar([i - w / 2 for i in x], li, width=w, color=NAVY, label="License Included")
    ax.bar([i + w / 2 for i in x], by, width=w, color=GREEN, label="BYOL")
    ax.set_xticks(list(x)); ax.set_xticklabels(vols)
    ax.set_title("OCI run cost by annual renewal volume", color=NAVY, fontsize=12, fontweight="bold")
    ax.set_ylabel("USD / year", color=SLATE)
    ax.legend(frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_facecolor(PAPER)
    fig.savefig(DIST / "bom.png", bbox_inches="tight", facecolor=PAPER)
    plt.close(fig)


if __name__ == "__main__":
    architecture(); process(); roi_waterfall(); tco(); bom()
    for p in ("architecture", "process", "roi_waterfall", "tco", "bom"):
        f = DIST / f"{p}.png"
        print(f"  {'OK' if f.exists() else '!!'}  {f.name} ({f.stat().st_size//1024} KB)")
