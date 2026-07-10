"""CLI: `quotepilot run <email files...> [--auto-approve]`"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import config
from .hitl import AutoApproveGate, CLIGate
from .orchestrator import run_autopilot


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="quotepilot",
        description="Email-to-quote autopilot agent (Qwen Cloud Hackathon, Track 4)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="Run the autopilot on inquiry email file(s)")
    run_p.add_argument("files", nargs="+", type=Path, help="Raw inquiry email text files")
    run_p.add_argument(
        "--auto-approve",
        action="store_true",
        help="Skip interactive approval (demo/CI); blocking flags still reject",
    )
    run_p.add_argument("--out", type=Path, default=None, help="Runs output dir")

    args = parser.parse_args(argv)

    gate = AutoApproveGate() if args.auto_approve else CLIGate()
    failures = 0
    for path in args.files:
        print(f"\n=== QuotePilot run: {path.name} " + "=" * 40)
        raw = path.read_text(encoding="utf-8")
        try:
            result = run_autopilot(raw, gate, runs_dir=args.out, source_name=path.name)
        except Exception as err:  # surface, keep batch going
            print(f"✗ run failed: {err}", file=sys.stderr)
            failures += 1
            continue
        print(f"\nDecision: {result.decision.action.upper()}"
              + (f" — {result.decision.notes}" if result.decision.notes else ""))
        for kind, apath in result.artifacts.items():
            print(f"  {kind:<12} {apath}")
        tokens = sum(
            u["prompt_tokens"] + u["completion_tokens"] for u in result.usage.values()
        )
        print(f"  tokens       {tokens:,} across {len(result.usage)} model(s): "
              + ", ".join(f"{m} ({u['calls']} calls)" for m, u in result.usage.items()))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
