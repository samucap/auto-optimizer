#!/usr/bin/env python3
"""Offline self-test: init temp workspace, success cycle, failure paths, module switch."""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPTS))

from paths import harness_root  # noqa: E402
from run_cycle import run_cycle  # noqa: E402
from workspace_init import init_workspace  # noqa: E402


def assert_true(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def main() -> int:
    live = "--live" in sys.argv
    tmp = Path(tempfile.mkdtemp(prefix="ao-self-test-"))
    print(f"self-test workspace: {tmp}")
    try:
        # fake git root optional — use --local style via project_root
        hroot = init_workspace(project_root=tmp, with_self_test=True, force=True)
        assert_true(hroot == tmp / ".grok" / "auto-optimizer", f"hroot {hroot}")
        assert_true((hroot / "modules" / "_template" / "module.yaml").exists(), "template missing")
        assert_true((tmp / ".gitignore").exists(), "gitignore missing")
        gi = (tmp / ".gitignore").read_text()
        assert_true(".grok/" in gi or ".grok" in gi, "expected .grok/ in gitignore")

        # 1) success cycle offline
        report = run_cycle(
            module="_template",
            project_root=tmp,
            local=True,
            offline=True,
            live=False,
        )
        assert_true(report["status"] == "success", f"expected success got {report}")
        assert_true(report.get("kept") is True, f"expected kept true: {report}")
        print("OK success cycle + keep")

        # 2) schema failure
        report = run_cycle(
            module="self-test",
            project_root=tmp,
            local=True,
            offline=True,
            force_fail="schema",
        )
        assert_true(report["status"] == "failed", f"schema fail status: {report['status']}")
        assert_true((hroot / "next_cycle_hints.md").exists(), "missing next_cycle_hints")
        print("OK schema failure + hints")

        # 3) eval failure
        report = run_cycle(
            module="self-test",
            project_root=tmp,
            local=True,
            offline=True,
            force_fail="eval",
        )
        assert_true(report["status"] == "failed", f"eval fail: {report}")
        assert_true("executor" in (report.get("failed_stages") or []) or report.get("root_cause"), report)
        print("OK eval failure report")

        # 4) reward hack
        report = run_cycle(
            module="self-test",
            project_root=tmp,
            local=True,
            offline=True,
            force_fail="reward_hack",
        )
        assert_true(report["status"] == "failed", f"reward hack: {report}")
        print("OK reward hack discard")

        # 5) budget exhausted
        report = run_cycle(
            module="self-test",
            project_root=tmp,
            local=True,
            offline=True,
            force_fail="budget",
        )
        assert_true(report["status"] == "budget_exhausted", f"budget: {report}")
        print("OK budget_exhausted")

        # 6) module switch
        report = run_cycle(
            module="_template",
            project_root=tmp,
            local=True,
            offline=True,
        )
        assert_true(report["module"] == "_template", report)
        print("OK module switch back to _template")

        # results log exists
        assert_true((hroot / "results.tsv").exists(), "results.tsv")
        assert_true((hroot / "results.jsonl").stat().st_size > 0, "results.jsonl empty")

        if live:
            print("NOTE: --live multi-subagent smoke not automated here; use: auto-optimizer once --live")

        print("SELF-TEST PASSED")
        return 0
    except Exception as e:
        print(f"SELF-TEST FAILED: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return 1
    finally:
        # keep tmp on failure for debug? always clean for CI friendliness
        if "--keep" not in sys.argv:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
