"""
================================================================================
 Syntax Corporation © 2026 — All Rights Reserved
--------------------------------------------------------------------------------
 Project : EBS Contract Renewal PAF — BPA Renewal Automation Agent
 Module  : deliverables/build_roi_calculator.py — interactive ROI calculator
 Version : 1.0.0      Build : 2026.06.04      Date : 2026-06-04
--------------------------------------------------------------------------------
 Emits a self-contained, Syntax-branded dist/roi_calculator.html with live
 sliders (volume, current cost/txn, target STP%, automated/assisted cost, term),
 computing net savings, payback months, 3-year cumulative + ROI. Defaults are
 pre-filled from the one pricing model (pricing.py) so the leave-behind matches
 the SOW and deck.
================================================================================
"""

from __future__ import annotations

import json
from pathlib import Path

import pricing

DIST = Path(__file__).resolve().parent / "dist"
DIST.mkdir(parents=True, exist_ok=True)

HTML = """<!DOCTYPE html>
<!-- Syntax Corporation © 2026 — EBS Contract Renewal PAF — ROI calculator -->
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>EBS Contract Renewal PAF — ROI Calculator · Syntax Corporation</title>
<style>
 :root{--navy:#0632A0;--navydk:#041F66;--green:#3CC85A;--cyan:#1EB4E6;
   --gold:#F1D488;--ink:#16203A;--slate:#5B6577;--mist:#F4F7FC;--line:#DCE4F4;}
 *{box-sizing:border-box} body{margin:0;font-family:Calibri,Segoe UI,Arial,sans-serif;
   color:var(--ink);background:var(--mist)}
 header{background:var(--navydk);color:#fff;padding:22px 32px}
 header .tri{display:inline-block;width:0;height:0;border-left:9px solid transparent;
   border-right:9px solid transparent;border-bottom:16px solid var(--green);margin-right:10px;vertical-align:middle}
 header h1{font-family:Georgia,serif;font-size:24px;margin:0;display:inline-block;vertical-align:middle}
 header p{margin:6px 0 0;color:#cfe0ff;font-size:13px}
 .wrap{max-width:1080px;margin:24px auto;padding:0 24px;display:grid;
   grid-template-columns:1fr 1fr;gap:24px}
 .card{background:#fff;border:1px solid var(--line);border-radius:12px;padding:22px}
 .card h2{font-family:Georgia,serif;color:var(--navy);font-size:17px;margin:0 0 14px}
 .row{margin:14px 0} label{display:flex;justify-content:space-between;font-size:13px;
   color:var(--slate);font-weight:bold;margin-bottom:6px}
 label b{color:var(--navy)} input[type=range]{width:100%;accent-color:var(--navy)}
 .kpis{grid-column:1/3;display:grid;grid-template-columns:repeat(4,1fr);gap:16px}
 .kpi{background:#fff;border:1px solid var(--line);border-radius:12px;padding:18px;text-align:center}
 .kpi .v{font-family:Georgia,serif;font-size:28px;color:var(--navy);font-weight:bold}
 .kpi.good .v{color:var(--green)} .kpi .l{font-size:12px;color:var(--slate);margin-top:4px}
 .bar{height:26px;border-radius:6px;background:var(--line);overflow:hidden;margin-top:8px}
 .bar>span{display:block;height:100%;background:var(--green)}
 footer{max-width:1080px;margin:8px auto 32px;padding:0 24px;color:var(--slate);font-size:11px}
 table{width:100%;border-collapse:collapse;font-size:13px} td{padding:6px 0;border-bottom:1px solid var(--line)}
 td.r{text-align:right;font-weight:bold;color:var(--ink)}
</style></head><body>
<header><span class="tri"></span><h1>EBS Contract Renewal PAF — ROI Calculator</h1>
<p>Syntax Corporation · Private Agent Factory · figures pre-filled from the engagement pricing model</p></header>
<div class="wrap">
 <div class="card"><h2>Your renewal volumes & cost</h2>
  <div class="row"><label>Agreements renewed / year <b id="vL"></b></label>
    <input id="v" type="range" min="200" max="40000" step="100"></div>
  <div class="row"><label>Current manual cost / renewal <b id="cL"></b></label>
    <input id="c" type="range" min="40" max="500" step="5"></div>
  <div class="row"><label>Target straight-through % <b id="sL"></b></label>
    <input id="s" type="range" min="0" max="100" step="1"></div>
 </div>
 <div class="card"><h2>Automation & commercials</h2>
  <div class="row"><label>Automated cost / renewal <b id="aL"></b></label>
    <input id="a" type="range" min="2" max="60" step="1"></div>
  <div class="row"><label>Assisted (exception) cost / renewal <b id="xL"></b></label>
    <input id="x" type="range" min="20" max="160" step="5"></div>
  <div class="row"><label>Managed-services term <b id="tL"></b></label>
    <input id="t" type="range" min="0" max="2" step="1"></div>
  <table><tr><td>One-time implementation</td><td class="r" id="impl"></td></tr>
   <tr><td>Annual run cost (managed services)</td><td class="r" id="run"></td></tr></table>
 </div>
 <div class="kpis">
  <div class="kpi good"><div class="v" id="k_save"></div><div class="l">Net annual savings</div></div>
  <div class="kpi"><div class="v" id="k_pay"></div><div class="l">Payback (months)</div></div>
  <div class="kpi good"><div class="v" id="k_3yr"></div><div class="l">3-year net savings</div></div>
  <div class="kpi"><div class="v" id="k_roi"></div><div class="l">3-year ROI</div></div>
 </div>
 <div class="card" style="grid-column:1/3"><h2>Straight-through processing</h2>
   <div class="bar"><span id="stpbar"></span></div>
   <p style="font-size:12px;color:var(--slate)" id="stpnote"></p></div>
</div>
<footer>Syntax Corporation © 2026 · Confidential — illustrative model; validate against your EBS data in a read-only value assessment.</footer>
<script>
const M = __MODEL__;
const TERMS = ["12","24","36"];
const $ = id => document.getElementById(id);
function fmt(n){return "$"+Math.round(n).toLocaleString()}
function init(){
  $("v").value=M.roi.annual_volume; $("c").value=M.roi.current_cost_per_txn;
  $("s").value=M.roi.target_stp_pct; $("a").value=M.roi.automated_cost_per_txn;
  $("x").value=M.roi.assisted_cost_per_txn; $("t").value=0;
  ["v","c","s","a","x","t"].forEach(id=>$(id).addEventListener("input",calc));
  calc();
}
function calc(){
  const v=+$("v").value,c=+$("c").value,s=+$("s").value/100,a=+$("a").value,
        x=+$("x").value,ti=+$("t").value, term=TERMS[ti];
  $("vL").textContent=v.toLocaleString(); $("cL").textContent=fmt(c);
  $("sL").textContent=s*100+"%"; $("aL").textContent=fmt(a); $("xL").textContent=fmt(x);
  $("tL").textContent=term+" months";
  const cur=v*c, fut=v*s*a + v*(1-s)*x, save=cur-fut;
  const impl=M.implementation.fixed_fee;
  const run=M.managed_services.terms[term].annual;
  $("impl").textContent=fmt(impl); $("run").textContent=fmt(run);
  const net=save-run;
  const payback = net>0 ? (impl/(net/12)) : null;
  const net3 = save*3 - (impl+run*3);
  const cost3 = impl+run*3;
  $("k_save").textContent=fmt(net);
  $("k_pay").textContent = payback? payback.toFixed(1):"—";
  $("k_3yr").textContent=fmt(net3);
  $("k_roi").textContent = (net3/cost3*100).toFixed(0)+"%";
  $("stpbar").style.width=(s*100)+"%";
  $("stpnote").textContent = Math.round(v*s).toLocaleString()+" renewals/yr fully automated, "
    +Math.round(v*(1-s)).toLocaleString()+" agent-assisted exceptions.";
}
init();
</script></body></html>
"""


def main() -> None:
    model = pricing.model()
    html = HTML.replace("__MODEL__", json.dumps(model))
    out = DIST / "roi_calculator.html"
    out.write_text(html)
    print(f"  OK  {out.name} ({out.stat().st_size//1024} KB)")


if __name__ == "__main__":
    main()
