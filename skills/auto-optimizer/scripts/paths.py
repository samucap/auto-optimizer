"""Resolve skill root, project workspace, and harness paths under .grok/auto-optimizer/."""

from __future__ import annotations

import os
from pathlib import Path


HARNESS_DIRNAME = "auto-optimizer"
GROK_DIRNAME = ".grok"


def skill_root() -> Path:
    """Directory containing SKILL.md (skills/auto-optimizer)."""
    return Path(__file__).resolve().parent.parent


def scripts_dir() -> Path:
    return Path(__file__).resolve().parent


def templates_dir() -> Path:
    return skill_root() / "templates"


def find_git_root(start: Path | None = None) -> Path | None:
    cur = (start or Path.cwd()).resolve()
    for p in [cur, *cur.parents]:
        if (p / ".git").exists():
            return p
    return None


def resolve_project_root(*, local: bool = False, cwd: Path | None = None) -> Path:
    """Project root that owns .grok/auto-optimizer/.

    Default: walk up to git root; --local uses CWD.
    """
    base = (cwd or Path.cwd()).resolve()
    if local:
        return base
    git = find_git_root(base)
    return git if git is not None else base


def harness_root(project_root: Path | None = None, *, local: bool = False) -> Path:
    """<project>/.grok/auto-optimizer/"""
    root = project_root if project_root is not None else resolve_project_root(local=local)
    return root / GROK_DIRNAME / HARNESS_DIRNAME


def modules_dir(hroot: Path) -> Path:
    return hroot / "modules"


def module_dir(hroot: Path, name: str) -> Path:
    return modules_dir(hroot) / name


def experiments_dir(hroot: Path) -> Path:
    return hroot / "experiments"


def cycle_dir(hroot: Path, module: str, cycle_id: str) -> Path:
    return experiments_dir(hroot) / module / cycle_id


def active_module_path(hroot: Path) -> Path:
    return hroot / "active_module"


def state_path(hroot: Path) -> Path:
    return hroot / "state.json"


def status_path(hroot: Path) -> Path:
    return hroot / "STATUS.md"


def results_tsv_path(hroot: Path) -> Path:
    return hroot / "results.tsv"


def results_jsonl_path(hroot: Path) -> Path:
    return hroot / "results.jsonl"


def stop_file_path(hroot: Path) -> Path:
    return hroot / "STOP"


def loop_log_path(hroot: Path) -> Path:
    return hroot / "loop.log"


def next_cycle_hints_path(hroot: Path) -> Path:
    return hroot / "next_cycle_hints.md"


def next_cycle_adjustments_path(hroot: Path) -> Path:
    return hroot / "next_cycle_adjustments.json"


def env_flag(name: str, default: bool = False) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "on"}
