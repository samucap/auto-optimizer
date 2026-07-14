"""Load and validate module.yaml; resolve active module pointer."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml

from paths import (
    active_module_path,
    harness_root,
    module_dir,
    modules_dir,
    resolve_project_root,
)


REQUIRED_TOP = ("name", "topic", "goal", "metrics", "eval")


def read_active_module_name(hroot: Path, override: str | None = None) -> str:
    if override:
        return override.strip()
    ap = active_module_path(hroot)
    if not ap.exists():
        raise FileNotFoundError(
            f"No active module. Pass --module or write {ap}"
        )
    name = ap.read_text(encoding="utf-8").strip()
    if not name:
        raise ValueError(f"active_module file is empty: {ap}")
    return name


def set_active_module(hroot: Path, name: str) -> None:
    hroot.mkdir(parents=True, exist_ok=True)
    active_module_path(hroot).write_text(name.strip() + "\n", encoding="utf-8")


def load_module_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"module.yaml not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"module.yaml must be a mapping: {path}")
    return data


def validate_module(mod: dict[str, Any], *, path: Path | None = None) -> list[str]:
    errors: list[str] = []
    for key in REQUIRED_TOP:
        if key not in mod:
            errors.append(f"missing required field: {key}")
    metrics = mod.get("metrics") or {}
    if isinstance(metrics, dict):
        if "primary" not in metrics:
            errors.append("metrics.primary is required")
        if "direction" not in metrics:
            errors.append("metrics.direction is required (minimize|maximize)")
        elif metrics["direction"] not in ("minimize", "maximize"):
            errors.append("metrics.direction must be minimize or maximize")
    else:
        errors.append("metrics must be a mapping")
    ev = mod.get("eval") or {}
    if isinstance(ev, dict):
        if not ev.get("command") and not (path and (path.parent / "eval.py").exists()):
            # command optional if module-local eval.py exists
            pass
    else:
        errors.append("eval must be a mapping")
    return errors


def load_module(
    *,
    module: str | None = None,
    project_root: Path | None = None,
    local: bool = False,
    hroot: Path | None = None,
) -> tuple[str, Path, dict[str, Any]]:
    """Return (name, module_dir, module_dict)."""
    if hroot is None:
        root = project_root or resolve_project_root(local=local)
        hroot = harness_root(root)
    name = read_active_module_name(hroot, module)
    mdir = module_dir(hroot, name)
    ypath = mdir / "module.yaml"
    mod = load_module_yaml(ypath)
    # Prefer directory name if yaml name differs; keep yaml name as canonical when present
    if mod.get("name") and mod["name"] != name:
        # allow alias but warn via stderr
        print(
            f"warning: module dir '{name}' != module.yaml name '{mod['name']}'",
            file=sys.stderr,
        )
    errs = validate_module(mod, path=ypath)
    if errs:
        raise ValueError(f"invalid module {ypath}: " + "; ".join(errs))
    return name, mdir, mod


def list_modules(hroot: Path) -> list[str]:
    md = modules_dir(hroot)
    if not md.exists():
        return []
    names = []
    for p in sorted(md.iterdir()):
        if p.is_dir() and (p / "module.yaml").exists() and not p.name.startswith("."):
            names.append(p.name)
    return names


def default_budgets(mod: dict[str, Any]) -> dict[str, Any]:
    b = dict(mod.get("budgets") or {})
    b.setdefault("max_cycles", 20)
    b.setdefault("max_reviewer_iterations", 3)
    b.setdefault("max_architect_candidates", 5)
    b.setdefault("max_executor_candidates", 4)
    b.setdefault("max_wall_time_minutes", 180)
    return b


def stage_config(mod: dict[str, Any], stage: str) -> dict[str, Any]:
    stages = mod.get("stages") or {}
    cfg = dict(stages.get(stage) or {})
    cfg.setdefault("enabled", True)
    if stage == "architect":
        cfg.setdefault("candidates", (mod.get("budgets") or {}).get("max_architect_candidates", 3))
    if stage == "executor":
        cfg.setdefault("candidates", (mod.get("budgets") or {}).get("max_executor_candidates", 2))
    if stage == "researcher":
        cfg.setdefault("web", True)
        cfg.setdefault("min_sources", 3)
    return cfg


if __name__ == "__main__":
    import argparse
    import json

    ap = argparse.ArgumentParser(description="Load and print active module")
    ap.add_argument("--module", default=None)
    ap.add_argument("--local", action="store_true")
    ap.add_argument("--project-root", type=Path, default=None)
    args = ap.parse_args()
    name, mdir, mod = load_module(
        module=args.module, project_root=args.project_root, local=args.local
    )
    print(json.dumps({"name": name, "dir": str(mdir), "module": mod}, indent=2, default=str))
