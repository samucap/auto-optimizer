"""Atomic state.json / STATUS.md persistence with last-good .prev fallback."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from paths import state_path, status_path


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        # Keep previous good file
        if path.exists():
            prev = path.with_suffix(path.suffix + ".prev")
            try:
                path.replace(prev)
            except OSError:
                pass
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def atomic_write_json(path: Path, data: Any) -> None:
    atomic_write_text(path, json.dumps(data, indent=2, sort_keys=True) + "\n")


def load_json(path: Path) -> Any | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def load_state(hroot: Path) -> dict[str, Any]:
    sp = state_path(hroot)
    data = load_json(sp)
    if data is not None and isinstance(data, dict):
        return data
    prev = load_json(sp.with_suffix(sp.suffix + ".prev"))
    if prev is not None and isinstance(prev, dict):
        return prev
    return default_state()


def default_state() -> dict[str, Any]:
    return {
        "version": 1,
        "module": None,
        "status": "idle",
        "cycle_id": None,
        "cycle_index": 0,
        "started_at": None,
        "updated_at": _utc_now(),
        "budgets": {},
        "spend": {
            "cycles_completed": 0,
            "reviewer_iterations": 0,
            "architect_candidates_run": 0,
            "executor_candidates_run": 0,
        },
        "last_good_cycle": None,
        "last_error": None,
        "active_stage": None,
        "pending_adjustments": None,
    }


def save_state(hroot: Path, state: dict[str, Any]) -> None:
    state = dict(state)
    state["updated_at"] = _utc_now()
    atomic_write_json(state_path(hroot), state)
    write_status_md(hroot, state)


def write_status_md(hroot: Path, state: dict[str, Any]) -> None:
    lines = [
        "# Auto-Optimizer Status",
        "",
        f"- **module**: `{state.get('module')}`",
        f"- **status**: `{state.get('status')}`",
        f"- **cycle_id**: `{state.get('cycle_id')}`",
        f"- **cycle_index**: {state.get('cycle_index')}",
        f"- **active_stage**: `{state.get('active_stage')}`",
        f"- **updated_at**: {state.get('updated_at')}",
        f"- **last_good_cycle**: `{state.get('last_good_cycle')}`",
        f"- **last_error**: {state.get('last_error')}",
        f"- **spend**: `{json.dumps(state.get('spend') or {})}`",
        "",
    ]
    if state.get("pending_adjustments"):
        lines.append("## Pending adjustments")
        lines.append("```json")
        lines.append(json.dumps(state["pending_adjustments"], indent=2))
        lines.append("```")
        lines.append("")
    atomic_write_text(status_path(hroot), "\n".join(lines))


def new_cycle_id() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    suffix = os.urandom(4).hex()
    return f"{ts}-{suffix}"
