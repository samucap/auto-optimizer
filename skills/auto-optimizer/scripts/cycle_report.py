"""Build and write mandatory per-cycle reports."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from state import atomic_write_json, atomic_write_text


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_report(
    *,
    cycle_id: str,
    module: str,
    status: str,
    root_cause: str | None = None,
    failed_stages: list[str] | None = None,
    failed_subagents: list[dict[str, Any]] | None = None,
    partial_progress: dict[str, Any] | None = None,
    scores: dict[str, Any] | None = None,
    kept: bool = False,
    recommendation: str | None = None,
    errors_path: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if status not in ("success", "failed", "budget_exhausted"):
        raise ValueError(f"invalid cycle status: {status}")
    report: dict[str, Any] = {
        "cycle_id": cycle_id,
        "module": module,
        "status": status,
        "root_cause": root_cause,
        "failed_stages": failed_stages or [],
        "failed_subagents": failed_subagents or [],
        "partial_progress": partial_progress or {},
        "scores": scores or {},
        "kept": kept,
        "recommendation": recommendation
        or _default_recommendation(status, root_cause),
        "errors_path": errors_path,
        "generated_at": _utc_now(),
    }
    if extra:
        report["extra"] = extra
    return report


def _default_recommendation(status: str, root_cause: str | None) -> str:
    if status == "success":
        return "Continue with next cycle; consider tightening metrics if plateauing."
    if status == "budget_exhausted":
        return (
            "Increase budgets or reduce candidate counts; "
            f"address: {root_cause or 'budget limits'}."
        )
    return f"Inspect failed stages and next_cycle_hints; root cause: {root_cause or 'unknown'}."


def write_cycle_report(cycle_dir: Path, report: dict[str, Any]) -> tuple[Path, Path]:
    cycle_dir.mkdir(parents=True, exist_ok=True)
    jpath = cycle_dir / "cycle_report.json"
    mpath = cycle_dir / "cycle_report.md"
    atomic_write_json(jpath, report)
    md = [
        f"# Cycle Report: {report['cycle_id']}",
        "",
        f"- **module**: `{report['module']}`",
        f"- **status**: `{report['status']}`",
        f"- **kept**: {report['kept']}",
        f"- **root_cause**: {report.get('root_cause')}",
        f"- **recommendation**: {report.get('recommendation')}",
        "",
        "## Failed stages",
        "",
    ]
    if report.get("failed_stages"):
        for s in report["failed_stages"]:
            md.append(f"- {s}")
    else:
        md.append("- (none)")
    md.extend(["", "## Scores", "", "```json", json.dumps(report.get("scores") or {}, indent=2), "```", ""])
    md.extend(
        [
            "## Partial progress",
            "",
            "```json",
            json.dumps(report.get("partial_progress") or {}, indent=2),
            "```",
            "",
        ]
    )
    atomic_write_text(mpath, "\n".join(md))
    return jpath, mpath
