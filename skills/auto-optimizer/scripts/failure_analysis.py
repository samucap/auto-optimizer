"""Analyze failed cycles and write next_cycle_hints + adjustments."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from paths import next_cycle_adjustments_path, next_cycle_hints_path
from state import atomic_write_json, atomic_write_text


def analyze_failure(report: dict[str, Any], errors: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Classify failure and propose safe adjustments + human hints."""
    status = report.get("status")
    root = (report.get("root_cause") or "").lower()
    failed_stages = report.get("failed_stages") or []
    errors = errors or []

    category = "unknown"
    hints: list[str] = []
    adjustments: dict[str, Any] = {"version": 1, "auto_apply": {}}

    if status == "budget_exhausted":
        category = "budget"
        hints.append("Reviewer or wall-time budget exhausted.")
        hints.append("Reduce architect/executor candidate counts or raise max_reviewer_iterations.")
        adjustments["auto_apply"]["suggest_reduce_candidates"] = True
    elif any("schema" in (s or "").lower() for s in failed_stages) or "schema" in root:
        category = "schema"
        hints.append("Dynamic schema validation failed after retry.")
        hints.append("Simplify output schema; require fewer nested fields next cycle.")
        adjustments["auto_apply"]["schema_simplify_hint"] = True
    elif any("eval" in (s or "").lower() for s in failed_stages) or "eval" in root:
        category = "eval"
        hints.append("Evaluation failed or metrics did not improve.")
        hints.append("Re-check eval command, fixtures, and anti-reward-hack false positives.")
        adjustments["auto_apply"]["bump_eval_timeout_once"] = True
    elif "worktree" in root or "git" in root:
        category = "worktree"
        hints.append("Git/worktree isolation failed; next cycle may use sandbox dirs.")
        adjustments["auto_apply"]["prefer_sandbox_dirs"] = True
    elif "reward" in root or "hack" in root:
        category = "reward_hack"
        hints.append("Candidate discarded for reward hacking.")
        hints.append("Do not edit eval harness, delete tests, or hardcode metric constants.")
    elif "interrupt" in root:
        category = "interrupted"
        hints.append("Previous cycle was interrupted; resume cleanly with a new cycle_id.")
    elif failed_stages:
        category = "stage_failure"
        hints.append(f"Failed stages: {', '.join(failed_stages)}")
        hints.append("Focus research and architecture on unblocking the first failed stage.")
    else:
        hints.append(report.get("recommendation") or "Inspect cycle_report.json and errors.jsonl.")

    if errors:
        hints.append(f"Logged {len(errors)} structured error event(s).")

    analysis = {
        "category": category,
        "hints": hints,
        "adjustments": adjustments,
        "source_status": status,
        "root_cause": report.get("root_cause"),
        "failed_stages": failed_stages,
    }
    return analysis


def write_failure_artifacts(hroot: Path, cycle_dir: Path, analysis: dict[str, Any]) -> None:
    hints_md = [
        "# Next cycle hints (from failure analysis)",
        "",
        f"**Category:** `{analysis.get('category')}`",
        f"**Root cause:** {analysis.get('root_cause')}",
        "",
        "## Hints",
        "",
    ]
    for h in analysis.get("hints") or []:
        hints_md.append(f"- {h}")
    hints_md.extend(
        [
            "",
            "## Adjustments (JSON)",
            "",
            "```json",
            json.dumps(analysis.get("adjustments") or {}, indent=2),
            "```",
            "",
            "The next cycle must load these hints into Researcher and Analyst prompts.",
            "",
        ]
    )
    text = "\n".join(hints_md)
    atomic_write_text(next_cycle_hints_path(hroot), text)
    atomic_write_json(next_cycle_adjustments_path(hroot), analysis)
    # copy into cycle dir
    atomic_write_text(cycle_dir / "next_cycle_hints.md", text)
    atomic_write_json(cycle_dir / "next_cycle_adjustments.json", analysis)


def load_pending_hints(hroot: Path) -> str:
    p = next_cycle_hints_path(hroot)
    if p.exists():
        return p.read_text(encoding="utf-8")
    return ""


def load_pending_adjustments(hroot: Path) -> dict[str, Any] | None:
    p = next_cycle_adjustments_path(hroot)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def clear_pending_hints(hroot: Path) -> None:
    for p in (next_cycle_hints_path(hroot), next_cycle_adjustments_path(hroot)):
        if p.exists():
            p.unlink()
