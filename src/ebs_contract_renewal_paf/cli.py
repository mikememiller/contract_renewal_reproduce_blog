"""
================================================================================
 Syntax Corporation © 2026 — All Rights Reserved
--------------------------------------------------------------------------------
 Project : EBS Contract Renewal PAF — BPA Renewal Automation Agent
 Module  : cli.py — command-line entry point
 Version : 1.0.0      Build : 2026.06.04      Date : 2026-06-04
--------------------------------------------------------------------------------
 Usage:
   python -m ebs_contract_renewal_paf <quote.txt> [--backend live|mock]
        [--extractor S] [--out output/] [--config conn.json] [--org-id 204]
        [--load-to-ebs --yes]

 Default backend is 'mock' (hermetic). Use '--backend live' to run against the
 EBS Vision database. Outputs the two PDOI interface CSVs, agent_trace.json and
 qa_report.json into the output directory.
================================================================================
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import BANNER
from .config import Settings
from .extractor import make_extractor
from .renewal_agent import RenewalAgent
from .repository import LiveEBSRepository, MockEBSRepository

_SAMPLE_DIR = Path(__file__).resolve().parents[2] / "sample_data"


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="ebs-renewal-paf",
                                description="EBS Contract Renewal PAF agent")
    p.add_argument("quote", help="path to the supplier renewal-quote text file")
    p.add_argument("--backend", choices=["mock", "live"], default=None)
    p.add_argument("--extractor", choices=["deterministic", "llm", "auto"],
                   default=None)
    p.add_argument("--out", default="output", help="output directory")
    p.add_argument("--config", default=None, help="JSON connection config")
    p.add_argument("--org-id", type=int, default=None)
    p.add_argument("--load-to-ebs", action="store_true",
                   help="INSERT loadable renewals into the PDOI interface tables")
    p.add_argument("--yes", action="store_true",
                   help="confirm the --load-to-ebs write")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    print(f"\n  {BANNER}")

    overrides = {"backend": args.backend, "org_id": args.org_id,
                 "extractor": args.extractor}
    settings = Settings.resolve(config_path=args.config, overrides=overrides)

    quote_text = Path(args.quote).read_text()
    extractor = make_extractor(settings.extractor, settings.llm_model)
    out_dir = Path(args.out)

    live_conn = None
    try:
        if settings.backend == "live":
            from .db import EBSConnection
            live_conn = EBSConnection(settings).__enter__()
            repo = LiveEBSRepository(live_conn, org_id=settings.org_id)
            qa_conn = live_conn
        else:
            repo = MockEBSRepository(_SAMPLE_DIR)
            qa_conn = None

        agent = RenewalAgent(repo, extractor, org_id=settings.org_id,
                             qa_conn=qa_conn)
        trace = agent.process(quote_text)
        hdr_csv, lines_csv = agent.flush(out_dir)

        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "agent_trace.json").write_text(
            json.dumps(trace.to_dict(), indent=2, default=str))
        (out_dir / "qa_report.json").write_text(
            json.dumps([r.to_dict() for r in agent.qa_reports], indent=2))

        _print_summary(trace, hdr_csv, lines_csv, out_dir)

        if args.load_to_ebs:
            _do_load(live_conn, agent, args.yes)

        # non-zero exit if QA failed (useful for CI / scheduling)
        return 0 if all(r.status != "FAIL" for r in agent.qa_reports) else 3
    finally:
        if live_conn is not None:
            live_conn.__exit__(None, None, None)


def _do_load(live_conn, agent, confirmed: bool) -> None:
    if live_conn is None:
        print("  --load-to-ebs requires --backend live; skipping.")
        return
    from .interface_loader import load_renewals
    result = load_renewals(live_conn, agent.writer.headers, agent.writer.lines,
                           agent.qa_reports, confirm=confirmed)
    print(f"  Loaded to EBS PDOI interface: {result}")


def _print_summary(trace, hdr_csv, lines_csv, out_dir) -> None:
    print("  " + "─" * 60)
    print(f"  Run ID            : {trace.run_id}")
    print(f"  Agreement         : {trace.agreement_num}")
    if trace.supplier_match:
        print(f"  Supplier matched  : {trace.supplier_match['vendor_name']} "
              f"(vendor_id={trace.supplier_match['vendor_id']})")
    else:
        print("  Supplier matched  : <none>")
    if trace.term and trace.term.get("term_months") is not None:
        print(f"  Proposed term     : "
              f"{_d(trace.term.get('new_effective_date'))} → "
              f"{_d(trace.term.get('new_expiration_date'))} "
              f"({trace.term.get('term_months')} months)")
    print(f"  Auto-approved     : {trace.auto_approved}")
    print(f"  Confidence        : {trace.confidence}")
    if trace.exceptions:
        print(f"  Header exceptions : {', '.join(trace.exceptions)}")
    if trace.qa:
        print(f"  QA status         : {trace.qa['status']} "
              f"(errors={trace.qa['error_count']}, holds={trace.qa['hold_count']})")
    for lr in trace.line_results:
        badge = "OK  AUTO" if lr["auto_approve"] else "!!  HOLD"
        excs = (" [" + ", ".join(lr["exceptions"]) + "]") if lr["exceptions"] else ""
        esc = (f" esc={lr['escalation_pct']}%"
               if lr.get("escalation_pct") is not None else "")
        print(f"    line {lr['line_number']:>2}  {badge}{esc}{excs}")
    print()
    print(f"  -> {hdr_csv}")
    print(f"  -> {lines_csv}")
    print(f"  -> {out_dir / 'agent_trace.json'}")
    print(f"  -> {out_dir / 'qa_report.json'}")
    print()


def _d(value) -> str:
    return str(value) if value is not None else "—"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
