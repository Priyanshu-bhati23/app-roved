"""Command line entry point: `approved scan MyApp.ipa`."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import ipa, llm, rag
from .catalog import load_catalog
from .checks import Settings
from .engine import analyze

_MARK = {"blocker": "✗", "warning": "!", "info": "·"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="approved", description="App Store compliance checks for an IPA")
    sub = parser.add_subparsers(dest="command", required=True)
    scan = sub.add_parser("scan", help="analyse an .ipa file")
    scan.add_argument("ipa", type=Path)
    scan.add_argument("--json", action="store_true", help="print the report as JSON")
    scan.add_argument("--no-explain", action="store_true", help="skip the RAG explanations")
    scan.add_argument("--min-sdk", default=Settings.min_sdk)
    sub.add_parser("signals", help="list the signal catalog")
    args = parser.parse_args(argv)

    if args.command == "signals":
        for s in load_catalog():
            print(f"{s.id:<11} {s.provenance.value:<24} {s.severity.value:<8} {s.title}")
        return 0

    try:
        bundle = ipa.load(args.ipa.read_bytes())
    except (OSError, ipa.IPAError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    report = analyze(bundle, Settings(min_sdk=args.min_sdk))
    if not args.no_explain:
        rag.explain_report(report, llm.from_env())

    if args.json:
        print(report.model_dump_json(indent=2))
    else:
        head = f"{report.app_name} {report.version or ''} ({report.bundle_id})  sdk={report.sdk}"
        print(f"{head}  -> {report.verdict.upper()}")
        for f in report.findings:
            s = f.signal
            print(f"\n {_MARK[s.severity.value]} {s.id} [{s.provenance.value}/{s.detection.value}] {s.title}")
            print(f"   evidence: {f.evidence}")
            if f.explanation:
                print(f"   {f.explanation.text}")
            if s.source:
                print(f"   source: {s.source}")
        c = report.counts
        print(f"\n{c['blocker']} blocker(s), {c['warning']} warning(s), {c['info']} info")
    # Non-zero exit on blockers so the command can gate a CI pipeline.
    return 1 if report.counts["blocker"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
