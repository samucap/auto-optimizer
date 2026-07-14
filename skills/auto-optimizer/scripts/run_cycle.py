#!/usr/bin/env python3
"""Run one auto-optimizer cycle (script path). Supports offline mock mode for self-test."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import traceback
from pathlib import Path
from typing import Any

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from cycle_report import build_report, write_cycle_report  # noqa: E402
from failure_analysis import (  # noqa: E402
    analyze_failure,
    clear_pending_hints,
    load_pending_adjustments,
    load_pending_hints,
    write_failure_artifacts,
)
from load_module import default_budgets, load_module, set_active_module, stage_config  # noqa: E402
from logging_util import log_event  # noqa: E402
from paths import (  # noqa: E402
    cycle_dir,
    harness_root,
    resolve_project_root,
    stop_file_path,
)
from results_log import append_result  # noqa: E402
from state import load_state, new_cycle_id, save_state  # noqa: E402
from keep_apply import apply_keep  # noqa: E402
from tournament import pick_winner  # noqa: E402
from validate_output import validate_files  # noqa: E402


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, default=str) + "\n", encoding="utf-8")


def _mock_stage(
    stage: str,
    artifact_dir: Path,
    mod: dict[str, Any],
    *,
    force_fail: str | None = None,
) -> dict[str, Any]:
    """Offline deterministic stage outputs for self-test / dry-run without grok."""
    artifact_dir.mkdir(parents=True, exist_ok=True)
    if force_fail == "schema":
        _write_json(artifact_dir / "output.json", {"wrong": True})
        _write_json(
            artifact_dir / "schema.json",
            {
                "type": "object",
                "required": ["summary", "hypotheses"],
                "properties": {
                    "summary": {"type": "string"},
                    "hypotheses": {"type": "array"},
                },
            },
        )
        return {"ok": False, "error": "schema_force_fail"}

    schema = {
        "type": "object",
        "required": ["summary", "stage"],
        "properties": {
            "summary": {"type": "string"},
            "stage": {"type": "string"},
            "hypotheses": {"type": "array"},
            "sources": {"type": "array"},
            "plan": {"type": "array"},
            "verdict": {"type": "string"},
        },
    }
    output: dict[str, Any] = {
        "summary": f"Mock {stage} output for module {mod.get('name')}",
        "stage": stage,
        "hypotheses": ["improve_primary_metric"],
        "sources": [{"title": "module.yaml", "url": "local", "why_trusted": "SSoT"}],
        "plan": ["edit sandbox score function"],
        "verdict": "approve",
    }
    _write_json(artifact_dir / "output.json", output)
    _write_json(artifact_dir / "schema.json", schema)
    (artifact_dir / "summary.md").write_text(output["summary"] + "\n", encoding="utf-8")
    errs = validate_files(artifact_dir / "output.json", artifact_dir / "schema.json")
    if errs:
        return {"ok": False, "error": "schema: " + "; ".join(errs)}
    return {"ok": True, "output": output}


def _run_sandbox_eval(mdir: Path, candidate_dir: Path) -> dict[str, Any]:
    """Invoke module eval.py via eval harness helpers."""
    from eval import run_eval

    return run_eval(
        module=None,
        candidate_dir=candidate_dir,
        baseline_dir=None,
        project_root=None,
        local=True,
        retries=0,
    )


def prepare_candidate_from_template(mdir: Path, candidate_dir: Path, *, improve: bool) -> None:
    """Copy sandbox into candidate_dir; optionally apply improved score.py."""
    if candidate_dir.exists():
        shutil.rmtree(candidate_dir)
    sandbox = mdir / "sandbox"
    if sandbox.exists():
        shutil.copytree(sandbox, candidate_dir / "sandbox")
    else:
        (candidate_dir / "sandbox").mkdir(parents=True)
    score = candidate_dir / "sandbox" / "score.py"
    if improve and score.exists():
        text = score.read_text(encoding="utf-8")
        # Apply the known improvement for _template
        text = text.replace("return n * 2  # baseline (suboptimal)", "return n * n  # optimized")
        text = text.replace("return n * 2", "return n * n")
        score.write_text(text, encoding="utf-8")


def run_cycle(
    *,
    module: str | None = None,
    project_root: Path | None = None,
    local: bool = False,
    offline: bool = False,
    dry_run: bool = False,
    force_fail: str | None = None,
    live: bool = False,
    keep_mode: str | None = None,
) -> dict[str, Any]:
    root = project_root or resolve_project_root(local=local)
    hroot = harness_root(root)
    if not hroot.exists():
        raise FileNotFoundError(
            f"Harness not initialized at {hroot}. Run: auto-optimizer init"
        )

    name, mdir, mod = load_module(
        module=module, project_root=root, local=local, hroot=hroot
    )
    set_active_module(hroot, name)
    budgets = default_budgets(mod)
    state = load_state(hroot)
    cycle_id = new_cycle_id()
    cdir = cycle_dir(hroot, name, cycle_id)
    cdir.mkdir(parents=True, exist_ok=True)
    err_log = cdir / "errors.jsonl"

    state.update(
        {
            "module": name,
            "status": "running",
            "cycle_id": cycle_id,
            "cycle_index": int(state.get("cycle_index") or 0) + 1,
            "started_at": state.get("started_at") or None,
            "active_stage": "init",
            "budgets": budgets,
            "last_error": None,
        }
    )
    if not state.get("started_at"):
        from datetime import datetime, timezone

        state["started_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    save_state(hroot, state)

    shutil.copy2(mdir / "module.yaml", cdir / "module_snapshot.yaml")
    hints = load_pending_hints(hroot)
    adjustments = load_pending_adjustments(hroot)
    if hints:
        (cdir / "consumed_hints.md").write_text(hints, encoding="utf-8")
    if adjustments:
        _write_json(cdir / "consumed_adjustments.json", adjustments)
        state["pending_adjustments"] = adjustments
        save_state(hroot, state)

    failed_stages: list[str] = []
    partial: dict[str, Any] = {}
    scores: dict[str, Any] = {}
    kept = False
    keep_meta: dict[str, Any] = {}
    status = "failed"
    root_cause: str | None = None
    recommendation: str | None = None

    use_offline = offline or dry_run or not live
    # Default script path is offline-safe unless --live
    if live:
        use_offline = False

    try:
        # --- Researcher ---
        state["active_stage"] = "researcher"
        save_state(hroot, state)
        rdir = cdir / "01_research"
        if stage_config(mod, "researcher").get("enabled", True):
            if use_offline:
                r = _mock_stage(
                    "researcher",
                    rdir,
                    mod,
                    force_fail="schema" if force_fail == "schema" else None,
                )
            else:
                from grok_spawn import (
                    build_stage_prompt,
                    load_persona_instructions,
                    run_grok_prompt,
                )

                persona = load_persona_instructions("ao-researcher")
                prompt = build_stage_prompt(
                    persona_instructions=persona,
                    stage="researcher",
                    module_yaml_text=(mdir / "module.yaml").read_text(encoding="utf-8"),
                    artifact_dir=rdir,
                    prior_context=hints or "",
                    extra="Perform comprehensive local + web research. Prefer official docs.",
                )
                rdir.mkdir(parents=True, exist_ok=True)
                gr = run_grok_prompt(prompt, cwd=root, log_path=err_log)
                r = {"ok": gr.get("ok"), "error": gr.get("error"), "raw": gr}
                if (rdir / "output.json").exists() and (rdir / "schema.json").exists():
                    verrs = validate_files(rdir / "output.json", rdir / "schema.json")
                    if verrs:
                        # one retry feedback is skill-path; script logs and fails stage
                        r = {"ok": False, "error": "schema: " + "; ".join(verrs)}
            partial["researcher"] = r
            if not r.get("ok"):
                failed_stages.append("researcher")
                root_cause = r.get("error") or "researcher failed"
                if force_fail == "schema":
                    status = "failed"
                    raise RuntimeError(root_cause)

        # --- Analyst ---
        state["active_stage"] = "analyst"
        save_state(hroot, state)
        adir = cdir / "02_analysis"
        if stage_config(mod, "analyst").get("enabled", True) and "researcher" not in failed_stages:
            if use_offline:
                a = _mock_stage("analyst", adir, mod)
            else:
                from grok_spawn import (
                    build_stage_prompt,
                    load_persona_instructions,
                    run_grok_prompt,
                )

                persona = load_persona_instructions("ao-analyst")
                prior = ""
                if (rdir / "output.json").exists():
                    prior = (rdir / "output.json").read_text(encoding="utf-8")
                prompt = build_stage_prompt(
                    persona_instructions=persona,
                    stage="analyst",
                    module_yaml_text=(mdir / "module.yaml").read_text(encoding="utf-8"),
                    artifact_dir=adir,
                    prior_context=prior + "\n\n" + (hints or ""),
                )
                adir.mkdir(parents=True, exist_ok=True)
                gr = run_grok_prompt(prompt, cwd=root, log_path=err_log)
                a = {"ok": gr.get("ok"), "error": gr.get("error")}
            partial["analyst"] = a
            if not a.get("ok"):
                failed_stages.append("analyst")
                root_cause = a.get("error") or "analyst failed"

        # --- Architect tournament (offline: single mock candidate) ---
        state["active_stage"] = "architect"
        save_state(hroot, state)
        arch_cfg = stage_config(mod, "architect")
        n_arch = int(arch_cfg.get("candidates") or 1)
        if use_offline:
            n_arch = 1
        arch_results: list[dict[str, Any]] = []
        for i in range(n_arch):
            cand = cdir / "03_architect" / f"c{i}"
            if use_offline:
                ar = _mock_stage(f"architect-{i}", cand, mod)
            else:
                from grok_spawn import (
                    build_stage_prompt,
                    load_persona_instructions,
                    run_grok_prompt,
                )

                persona = load_persona_instructions("ao-architect")
                prior = ""
                if (adir / "output.json").exists():
                    prior = (adir / "output.json").read_text(encoding="utf-8")
                prompt = build_stage_prompt(
                    persona_instructions=persona,
                    stage="architect",
                    module_yaml_text=(mdir / "module.yaml").read_text(encoding="utf-8"),
                    artifact_dir=cand,
                    prior_context=prior,
                    extra=f"You are architect candidate {i}. Propose a distinct approach.",
                )
                cand.mkdir(parents=True, exist_ok=True)
                gr = run_grok_prompt(
                    prompt, cwd=root, worktree=True, log_path=err_log
                )
                ar = {"ok": gr.get("ok"), "error": gr.get("error"), "candidate": i}
            ar["candidate"] = i
            ar["primary"] = float(i)  # placeholder rank offline
            ar["path"] = str(cand)
            if ar.get("ok"):
                ar["ok"] = True
                # treat mock as ok for tournament ranking
                arch_results.append(
                    {
                        "ok": True,
                        "primary": float(i),
                        "candidate": i,
                        "path": str(cand),
                        "reward_hack": False,
                    }
                )
            else:
                log_event(err_log, {"type": "architect_fail", "candidate": i, "error": ar.get("error")})
        direction = (mod.get("metrics") or {}).get("direction", "minimize")
        # For architect mock, lower candidate index is fine; pick first ok
        winner_arch = pick_winner(arch_results, direction="minimize") if arch_results else None
        if not winner_arch:
            failed_stages.append("architect")
            root_cause = root_cause or "all architect candidates failed"
        else:
            _write_json(cdir / "03_architect" / "winner.json", winner_arch)
            partial["architect_winner"] = winner_arch

        # --- Reviewer (architecture) ---
        state["active_stage"] = "reviewer_arch"
        save_state(hroot, state)
        rev_dir = cdir / "04_review"
        rev_dir.mkdir(parents=True, exist_ok=True)
        if use_offline:
            verdict = {
                "summary": "Mock approve architecture",
                "stage": "reviewer",
                "verdict": "approve",
            }
            _write_json(rev_dir / "verdict.json", verdict)
            (rev_dir / "round_1.md").write_text("# Review\n\nApprove.\n", encoding="utf-8")
            partial["reviewer_arch"] = {"ok": True, "verdict": "approve"}
        else:
            from grok_spawn import (
                build_stage_prompt,
                load_persona_instructions,
                run_grok_prompt,
            )

            persona = load_persona_instructions("ao-reviewer")
            prompt = build_stage_prompt(
                persona_instructions=persona,
                stage="reviewer",
                module_yaml_text=(mdir / "module.yaml").read_text(encoding="utf-8"),
                artifact_dir=rev_dir,
                prior_context=json.dumps(winner_arch or {}),
                extra="Adversarial review. verdict in verdict.json: approve|revise_architecture|reject",
            )
            gr = run_grok_prompt(prompt, cwd=root, log_path=err_log)
            partial["reviewer_arch"] = {"ok": gr.get("ok"), "error": gr.get("error")}

        # --- Executor tournament ---
        state["active_stage"] = "executor"
        save_state(hroot, state)
        n_exec = int(stage_config(mod, "executor").get("candidates") or 1)
        if use_offline:
            n_exec = 2 if force_fail != "eval" else 1
        exec_results: list[dict[str, Any]] = []
        primary_name = (mod.get("metrics") or {}).get("primary", "score")

        for i in range(n_exec):
            cand = cdir / "05_executor" / f"c{i}"
            improve = use_offline and i == 0 and force_fail != "eval"
            # candidate 0 improved, candidate 1 baseline (worse)
            prepare_candidate_from_template(mdir, cand, improve=improve)
            if force_fail == "eval" and i == 0:
                # break eval by removing score
                sp = cand / "sandbox" / "score.py"
                if sp.exists():
                    sp.write_text("def score(n):\n    raise RuntimeError('forced eval fail')\n", encoding="utf-8")
            if force_fail == "reward_hack" and i == 0:
                (cand / ".ao_touched_paths.txt").write_text(
                    "modules/_template/eval.py\n", encoding="utf-8"
                )
                (cand / "modules" / "_template").mkdir(parents=True, exist_ok=True)
                (cand / "modules" / "_template" / "eval.py").write_text("# hacked\n", encoding="utf-8")

            # Run eval with module forced via active_module
            set_active_module(hroot, name)
            from eval import run_eval

            er = run_eval(
                module=name,
                candidate_dir=cand,
                baseline_dir=None,
                project_root=root,
                local=local,
                retries=0 if force_fail == "eval" else None,
            )
            er["candidate"] = i
            er["path"] = str(cand)
            _write_json(cand / "scores.json", er)
            if er.get("ok") and er.get("primary") is not None:
                exec_results.append(er)
            else:
                log_event(
                    err_log,
                    {
                        "type": "executor_eval_fail",
                        "candidate": i,
                        "error": er.get("error"),
                        "reward_hack": er.get("reward_hack"),
                    },
                )
            partial.setdefault("executor", []).append(
                {"candidate": i, "ok": er.get("ok"), "primary": er.get("primary"), "error": er.get("error")}
            )

        winner = pick_winner(exec_results, direction=direction)
        if winner:
            _write_json(cdir / "05_executor" / "winner.json", winner)
            scores = {
                "primary_metric": primary_name,
                "winner": winner.get("primary"),
                "candidates": [
                    {"candidate": r.get("candidate"), "primary": r.get("primary")}
                    for r in exec_results
                ],
            }
            partial["executor_winner"] = {
                "candidate": winner.get("candidate"),
                "primary": winner.get("primary"),
                "path": winner.get("path"),
            }
        else:
            failed_stages.append("executor")
            root_cause = root_cause or "all executor candidates failed or discarded"
            if force_fail in ("eval", "reward_hack"):
                status = "failed"

        # --- Final reviewer ---
        state["active_stage"] = "reviewer_final"
        save_state(hroot, state)
        fr = cdir / "06_final_review"
        fr.mkdir(parents=True, exist_ok=True)
        if use_offline:
            _write_json(
                fr / "verdict.json",
                {"verdict": "approve" if winner else "reject", "summary": "mock final review"},
            )
            partial["reviewer_final"] = {"ok": True, "verdict": "approve" if winner else "reject"}
        else:
            from grok_spawn import (
                build_stage_prompt,
                load_persona_instructions,
                run_grok_prompt,
            )

            persona = load_persona_instructions("ao-reviewer")
            prompt = build_stage_prompt(
                persona_instructions=persona,
                stage="final_reviewer",
                module_yaml_text=(mdir / "module.yaml").read_text(encoding="utf-8"),
                artifact_dir=fr,
                prior_context=json.dumps(winner or {}),
                extra="Review executor output. Must approve before keep.",
            )
            gr = run_grok_prompt(prompt, cwd=root, log_path=err_log)
            partial["reviewer_final"] = {"ok": gr.get("ok")}

        # --- Keep / revert (proposal only — Karpathy-style) ---
        state["active_stage"] = "keep_revert"
        save_state(hroot, state)
        keep_policy = mod.get("keep_policy") or {}
        require_improved = keep_policy.get("require_primary_improved", True)

        if winner and not failed_stages:
            baseline_cand = cdir / "baseline_candidate"
            prepare_candidate_from_template(mdir, baseline_cand, improve=False)
            from eval import run_eval

            base_scores = run_eval(
                module=name,
                candidate_dir=baseline_cand,
                baseline_dir=None,
                project_root=root,
                local=local,
                retries=0,
            )
            scores["baseline"] = base_scores.get("primary")
            improved = True
            if base_scores.get("primary") is not None and winner.get("primary") is not None:
                if direction == "minimize":
                    improved = float(winner["primary"]) < float(base_scores["primary"])
                else:
                    improved = float(winner["primary"]) > float(base_scores["primary"])

            if require_improved and not improved:
                kept = False
                root_cause = None  # not a pipeline failure — no proposal
                status = "success"
                recommendation = (
                    "Eval did not improve primary metric; no proposal branch opened. "
                    "Inspect candidates and try next cycle."
                )
            else:
                findings = None
                summary_p = cdir / "01_research" / "summary.md"
                if summary_p.exists():
                    findings = summary_p.read_text(encoding="utf-8")[:4000]
                rec = (
                    "Proposal branch opened (not merged). Review AO_KEEP.md and metrics, "
                    "then merge only if you accept the change."
                )
                kr = apply_keep(
                    project_root=root,
                    module=name,
                    mdir=mdir,
                    candidate_dir=Path(winner["path"]),
                    cycle_id=cycle_id,
                    mod=mod,
                    scores=scores,
                    experiment_path=str(cdir),
                    recommendation=rec,
                    findings=findings,
                    dry_run=dry_run,
                    keep_mode=keep_mode,
                )
                keep_meta = kr.to_dict()
                _write_json(cdir / "keep.json", keep_meta)
                if kr.kept:
                    kept = True
                    status = "success"
                    root_cause = None
                    recommendation = rec
                    if kr.review_commands:
                        recommendation += "\n\n" + "\n".join(f"`{c}`" for c in kr.review_commands)
                    state["last_keep_branch"] = kr.branch
                    state["last_keep_sha"] = kr.commit_sha
                else:
                    kept = False
                    status = "failed"
                    root_cause = kr.error or "keep proposal failed"
                    failed_stages.append("keep")
                    log_event(err_log, {"type": "keep_failed", "keep": keep_meta})
        elif winner and force_fail is None and not any(
            s in failed_stages for s in ("researcher", "architect", "executor")
        ):
            status = "success"
            kept = False
        else:
            if force_fail == "budget":
                status = "budget_exhausted"
                root_cause = root_cause or "max_reviewer_iterations exceeded (forced)"
            else:
                status = "failed"
                root_cause = root_cause or "cycle failed"

        # Forced failure modes (self-test) override terminal status
        if force_fail == "budget":
            status = "budget_exhausted"
            root_cause = "max_reviewer_iterations exceeded (forced)"
            kept = False
            if "reviewer" not in failed_stages:
                failed_stages.append("reviewer")

    except Exception as e:
        log_event(err_log, {"type": "cycle_exception", "error": str(e), "tb": traceback.format_exc()})
        status = "budget_exhausted" if force_fail == "budget" else "failed"
        root_cause = root_cause or str(e)
        if "researcher" not in failed_stages and "schema" in str(e).lower():
            failed_stages.append("researcher")

    report = build_report(
        cycle_id=cycle_id,
        module=name,
        status=status if status in ("success", "failed", "budget_exhausted") else "failed",
        root_cause=root_cause,
        failed_stages=failed_stages,
        partial_progress=partial,
        scores=scores,
        kept=kept,
        recommendation=recommendation,
        errors_path=str(err_log) if err_log.exists() else None,
        extra={"keep": keep_meta} if keep_meta else None,
    )
    # kept=true means proposal opened, not merged into current branch
    if kept and keep_meta.get("mode") == "branch":
        report["recommendation"] = recommendation or report.get("recommendation")
    write_cycle_report(cdir, report)
    if keep_meta and not (cdir / "keep.json").exists():
        _write_json(cdir / "keep.json", keep_meta)

    if status != "success":
        analysis = analyze_failure(report)
        write_failure_artifacts(hroot, cdir, analysis)
        state["pending_adjustments"] = analysis
        state["last_error"] = root_cause
    else:
        clear_pending_hints(hroot)
        state["pending_adjustments"] = None
        state["last_good_cycle"] = cycle_id
        state["last_error"] = None
        spend = dict(state.get("spend") or {})
        spend["cycles_completed"] = int(spend.get("cycles_completed") or 0) + 1
        state["spend"] = spend

    state["status"] = status
    state["active_stage"] = "done"
    # state is loop control only; science lives in cycle_report + results_log (+ proposal branch)
    save_state(hroot, state)

    notes = root_cause or ""
    if keep_meta.get("branch"):
        notes = (
            f"proposal_branch={keep_meta.get('branch')} "
            f"commit={keep_meta.get('commit_sha')} merged=false"
        ).strip()
        if root_cause:
            notes = f"{root_cause}; {notes}"

    append_result(
        hroot,
        {
            "cycle_id": cycle_id,
            "module": name,
            "status": status,
            "primary_metric": (mod.get("metrics") or {}).get("primary"),
            "primary_value": scores.get("winner", ""),
            "baseline_value": scores.get("baseline", ""),
            "delta": "",
            "kept": kept,
            "notes": notes,
        },
    )

    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run one auto-optimizer cycle")
    ap.add_argument("--module", default=None)
    ap.add_argument("--project-root", type=Path, default=None)
    ap.add_argument("--local", action="store_true")
    ap.add_argument("--offline", action="store_true", help="No grok CLI; mock research stages")
    ap.add_argument("--live", action="store_true", help="Use grok CLI for agent stages")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument(
        "--keep-mode",
        choices=["auto", "branch", "inplace"],
        default=None,
        help="How to open a keep proposal (default: auto → branch if git else inplace)",
    )
    ap.add_argument(
        "--force-fail",
        choices=["schema", "eval", "reward_hack", "budget"],
        default=None,
    )
    args = ap.parse_args(argv)

    # Default offline for safety when not --live
    offline = args.offline or not args.live
    try:
        report = run_cycle(
            module=args.module,
            project_root=args.project_root,
            local=args.local,
            offline=offline,
            dry_run=args.dry_run,
            force_fail=args.force_fail,
            live=args.live,
            keep_mode=args.keep_mode,
        )
    except Exception as e:
        print(json.dumps({"status": "failed", "error": str(e)}), file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, default=str))
    return 0 if report.get("status") == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
