#!/usr/bin/env python3
"""Primary Python orchestrator for continuous / once cycles.

Uses run_cycle under the hood. Live multi-subagent work is delegated to grok CLI
when --live is set; otherwise offline-safe mocks for research stages + real eval.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPTS))

from paths import harness_root, resolve_project_root, stop_file_path  # noqa: E402
from run_cycle import run_cycle  # noqa: E402


def parse_interval(s: str) -> int:
    if s.endswith("s"):
        return int(s[:-1])
    if s.endswith("m"):
        return int(s[:-1]) * 60
    if s.endswith("h"):
        return int(s[:-1]) * 3600
    return int(s)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Auto-optimizer ACP/script orchestrator")
    ap.add_argument("--module", default=None)
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--max-cycles", type=int, default=None)
    ap.add_argument("--interval", default="0")
    ap.add_argument("--local", action="store_true")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--project-root", type=Path, default=None)
    ap.add_argument("--stop-on-fail", action="store_true")
    args = ap.parse_args(argv)

    root = args.project_root or resolve_project_root(local=args.local)
    hroot = harness_root(root)
    interval = parse_interval(args.interval) if args.interval else 0
    offline = args.offline or not args.live

    n = 0
    while True:
        if stop_file_path(hroot).exists():
            stop_file_path(hroot).unlink(missing_ok=True)
            print(json.dumps({"event": "stopped"}))
            break
        n += 1
        if args.max_cycles is not None and n > args.max_cycles:
            break
        report = run_cycle(
            module=args.module,
            project_root=root,
            local=args.local,
            offline=offline,
            live=args.live,
        )
        print(json.dumps({"event": "cycle_complete", "report": report}, default=str))
        if args.once:
            return 0 if report.get("status") == "success" else 1
        if args.stop_on_fail and report.get("status") != "success":
            return 1
        if interval > 0:
            time.sleep(interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
