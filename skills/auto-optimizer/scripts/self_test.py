#!/usr/bin/env python3
"""Offline self-test: init temp workspace, success cycle, failure paths, module switch."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPTS))

from keep_apply import collect_apply_plan  # noqa: E402
from run_cycle import run_cycle  # noqa: E402
from workspace_init import init_workspace  # noqa: E402


def assert_true(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def _test_collect_apply_plan(tmp: Path) -> None:
    """Module-local sandbox vs project-rooted paths."""
    cand = tmp / "_cand"
    (cand / "sandbox").mkdir(parents=True)
    (cand / "sandbox" / "score.py").write_text("x=1\n", encoding="utf-8")
    (cand / "skills" / "foo").mkdir(parents=True)
    (cand / "skills" / "foo" / "bar.py").write_text("y=2\n", encoding="utf-8")

    pairs = collect_apply_plan(
        project_root=tmp,
        module="m1",
        mdir=tmp / "mod",
        candidate_dir=cand,
        files_to_edit=["sandbox/score.py", "skills/foo/bar.py"],
    )
    norm = {Path(d).as_posix() for _, d in pairs}
    assert_true(
        ".grok/auto-optimizer/modules/m1/sandbox/score.py" in norm,
        f"expected module sandbox dest: {norm}",
    )
    assert_true(
        "skills/foo/bar.py" in norm,
        f"project path must stay project-relative: {norm}",
    )
    print("OK collect_apply_plan path mapping")


def _git(tmp: Path, *args: str) -> str:
    env = os.environ.copy()
    env.setdefault("GIT_AUTHOR_NAME", "ao-self-test")
    env.setdefault("GIT_AUTHOR_EMAIL", "ao-self-test@localhost")
    env.setdefault("GIT_COMMITTER_NAME", "ao-self-test")
    env.setdefault("GIT_COMMITTER_EMAIL", "ao-self-test@localhost")
    r = subprocess.run(
        ["git", *args],
        cwd=str(tmp),
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )
    return r.stdout.strip()


def main() -> int:
    live = "--live" in sys.argv
    tmp = Path(tempfile.mkdtemp(prefix="ao-self-test-"))
    print(f"self-test workspace: {tmp}")
    try:
        # Git repo so keep opens a *proposal branch* (not silent inplace merge)
        _git(tmp, "init")
        (tmp / "README.md").write_text("# ao self-test\n", encoding="utf-8")
        _git(tmp, "add", "README.md")
        _git(tmp, "commit", "-m", "init")

        hroot = init_workspace(project_root=tmp, with_self_test=True, force=True)
        assert_true(hroot == tmp / ".grok" / "auto-optimizer", f"hroot {hroot}")
        assert_true((hroot / "modules" / "_template" / "module.yaml").exists(), "template missing")
        assert_true((tmp / ".gitignore").exists(), "gitignore missing")
        gi = (tmp / ".gitignore").read_text()
        assert_true(".grok/" in gi or ".grok" in gi, "expected .grok/ in gitignore")

        head_before = _git(tmp, "rev-parse", "HEAD")
        sandbox_before = (hroot / "modules" / "_template" / "sandbox" / "score.py").read_text(
            encoding="utf-8"
        )

        # 1) success cycle offline → proposal branch keep
        report = run_cycle(
            module="_template",
            project_root=tmp,
            local=True,
            offline=True,
            live=False,
        )
        assert_true(report["status"] == "success", f"expected success got {report}")
        assert_true(report.get("kept") is True, f"expected kept true: {report}")

        keep_extra = (report.get("extra") or {}).get("keep") or {}
        cycle_id = report["cycle_id"]
        keep_path = hroot / "experiments" / "_template" / cycle_id / "keep.json"
        assert_true(keep_path.exists(), "keep.json missing")
        assert_true(
            (hroot / "experiments" / "_template" / cycle_id / "cycle_report.json").exists(),
            "cycle_report.json missing",
        )

        assert_true(keep_extra.get("mode") == "branch", f"expected branch keep: {keep_extra}")
        branch = keep_extra.get("branch")
        assert_true(bool(branch), f"missing branch: {keep_extra}")
        assert_true(bool(keep_extra.get("commit_sha")), f"missing commit_sha: {keep_extra}")
        assert_true(keep_extra.get("merged") is False, "proposal must not be auto-merged")

        # Main checkout unchanged
        head_after = _git(tmp, "rev-parse", "HEAD")
        assert_true(head_before == head_after, "HEAD should not move on keep proposal")
        sandbox_after = (hroot / "modules" / "_template" / "sandbox" / "score.py").read_text(
            encoding="utf-8"
        )
        assert_true(
            sandbox_before == sandbox_after,
            "working-tree module sandbox must not be mutated by branch keep",
        )

        # Proposal is reviewable on the branch (code + AO_CYCLE ledger)
        show = _git(tmp, "show", f"{branch}:AO_KEEP.md")
        assert_true("proposal" in show.lower() or "Auto-Optimizer" in show, show[:200])
        _git(tmp, "show", f"{branch}:AO_KEEP_SCORES.json")
        cycle_json = _git(tmp, "show", f"{branch}:AO_CYCLE/cycle_report.json")
        assert_true('"cycle_id"' in cycle_json or "cycle_id" in cycle_json, cycle_json[:200])
        cycle_md = _git(tmp, "show", f"{branch}:AO_CYCLE/cycle_report.md")
        assert_true("Cycle Report" in cycle_md or "cycle" in cycle_md.lower(), cycle_md[:200])
        print("OK success cycle + proposal branch keep (main tree unchanged, AO_CYCLE present)")

        _test_collect_apply_plan(tmp)

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
        assert_true(
            "executor" in (report.get("failed_stages") or []) or report.get("root_cause"),
            report,
        )
        print("OK eval failure report")

        # 4) reward hack: cheating candidate discarded; survivor may not beat baseline → no proposal
        report = run_cycle(
            module="self-test",
            project_root=tmp,
            local=True,
            offline=True,
            force_fail="reward_hack",
        )
        exec_partial = (report.get("partial_progress") or {}).get("executor") or []
        assert_true(
            any(
                (not e.get("ok"))
                and e.get("error")
                and "reward_hack" in str(e.get("error"))
                for e in exec_partial
            ),
            f"expected a reward_hack discard among executors: {exec_partial}",
        )
        assert_true(report.get("kept") is False, f"must not open proposal on pure hack path: {report}")
        print("OK reward hack discard (no proposal)")

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

        # 6) module switch + another proposal
        report = run_cycle(
            module="_template",
            project_root=tmp,
            local=True,
            offline=True,
        )
        assert_true(report["module"] == "_template", report)
        assert_true(report.get("kept") is True, report)
        print("OK module switch + second proposal")

        # results log exists (longitudinal ledger)
        assert_true((hroot / "results.tsv").exists(), "results.tsv")
        assert_true((hroot / "results.jsonl").stat().st_size > 0, "results.jsonl empty")
        tsv = (hroot / "results.tsv").read_text(encoding="utf-8")
        assert_true("proposal_branch=" in tsv or "ao/" in tsv, "results should note proposal")

        if live:
            print("NOTE: --live multi-subagent smoke not automated here; use once --live")

        print("SELF-TEST PASSED")
        return 0
    except Exception as e:
        print(f"SELF-TEST FAILED: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return 1
    finally:
        if "--keep" not in sys.argv:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
