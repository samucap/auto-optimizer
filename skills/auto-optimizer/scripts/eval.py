#!/usr/bin/env python3
"""Generic eval harness: load module, run module eval or command, anti-reward-hack checks."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

# Allow running as script from any CWD
_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from load_module import load_module  # noqa: E402
from paths import harness_root, resolve_project_root  # noqa: E402


def _run_module_eval_py(
    mdir: Path,
    candidate_dir: Path,
    baseline_dir: Path | None,
    mod: dict[str, Any],
    timeout: int,
) -> dict[str, Any]:
    eval_py = mdir / "eval.py"
    if not eval_py.exists():
        raise FileNotFoundError(f"no module eval.py at {eval_py}")
    cmd = [
        sys.executable,
        str(eval_py),
        "--candidate-dir",
        str(candidate_dir),
    ]
    if baseline_dir:
        cmd.extend(["--baseline-dir", str(baseline_dir)])
    env = os.environ.copy()
    env["AO_MODULE_DIR"] = str(mdir)
    env["AO_MODULE_YAML"] = str(mdir / "module.yaml")
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(mdir),
        env=env,
    )
    if proc.returncode != 0:
        return {
            "ok": False,
            "error": f"eval.py exit {proc.returncode}",
            "stderr": proc.stderr[-4000:],
            "stdout": proc.stdout[-4000:],
            "metrics": {},
            "gates_passed": False,
            "reward_hack": False,
            "reward_hack_reasons": [],
        }
    # Prefer last JSON object on stdout
    out = proc.stdout.strip()
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        # try last line
        for line in reversed(out.splitlines()):
            line = line.strip()
            if line.startswith("{"):
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    continue
        return {
            "ok": False,
            "error": "eval.py produced non-JSON stdout",
            "stdout": out[-4000:],
            "metrics": {},
            "gates_passed": False,
            "reward_hack": False,
            "reward_hack_reasons": [],
        }


def anti_reward_hack(
    mod: dict[str, Any],
    candidate_dir: Path,
    project_root: Path,
) -> list[str]:
    reasons: list[str] = []
    cfg = mod.get("anti_reward_hacking") or {}
    forbid = list(cfg.get("forbid_edit_globs") or [])
    forbid.extend(
        [
            "scripts/eval.py",
            "**/scripts/eval.py",
            ".grok/auto-optimizer/modules/*/eval.py",
            ".grok/auto-optimizer/modules/*/fixtures/**",
        ]
    )
    detect = set(cfg.get("detect") or ["deleted_tests", "eval_harness_mutation"])

    # Scan candidate_dir for suspicious paths if it contains a diff listing
    forbidden_hit = candidate_dir / ".ao_touched_paths.txt"
    touched: list[str] = []
    if forbidden_hit.exists():
        touched = [ln.strip() for ln in forbidden_hit.read_text().splitlines() if ln.strip()]
    else:
        # heuristic: list files under candidate that look like eval/test deletion markers
        for p in candidate_dir.rglob("*"):
            if p.is_file():
                rel = str(p.relative_to(candidate_dir))
                touched.append(rel)

    for t in touched:
        tl = t.replace("\\", "/")
        if "eval.py" in tl and "modules" in tl:
            if "eval_harness_mutation" in detect:
                reasons.append(f"eval harness mutation suspected: {t}")
        if re.search(r"test_.*\.(py|go|ts|js)$", tl) and tl.endswith(".deleted"):
            if "deleted_tests" in detect:
                reasons.append(f"deleted test marker: {t}")
        for g in forbid:
            # simple glob-ish contains check
            g_norm = g.replace("**/", "").replace("*", "")
            if g_norm and g_norm in tl:
                reasons.append(f"forbidden path touched: {t} (rule {g})")

    # Hardcoded metric constant heuristic in candidate score files
    if "hardcoded_metric_constants" in detect:
        for p in candidate_dir.rglob("*.py"):
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if re.search(r"return\s+0\.0\s*#\s*metric", text) or "AO_HARDCODE_METRIC" in text:
                reasons.append(f"hardcoded metric constant in {p.name}")

    return sorted(set(reasons))


def apply_gates(mod: dict[str, Any], metrics: dict[str, Any]) -> bool:
    secondary = (mod.get("metrics") or {}).get("secondary") or []
    for s in secondary:
        if not isinstance(s, dict):
            continue
        name = s.get("name")
        if not name or name not in metrics:
            if s.get("min_value") is not None or s.get("max_value") is not None:
                return False
            continue
        val = metrics[name]
        if s.get("min_value") is not None and val < s["min_value"]:
            return False
        if s.get("max_value") is not None and val > s["max_value"]:
            return False
    return True


def compare_primary(mod: dict[str, Any], primary: float, baseline: float | None) -> dict[str, Any]:
    direction = (mod.get("metrics") or {}).get("direction", "minimize")
    improved = None
    delta = None
    if baseline is not None:
        delta = primary - baseline
        if direction == "minimize":
            improved = primary < baseline
        else:
            improved = primary > baseline
    return {"delta": delta, "improved": improved, "direction": direction}


def run_eval(
    *,
    module: str | None,
    candidate_dir: Path,
    baseline_dir: Path | None,
    project_root: Path | None,
    local: bool,
    retries: int | None = None,
) -> dict[str, Any]:
    root = project_root or resolve_project_root(local=local)
    hroot = harness_root(root)
    name, mdir, mod = load_module(module=module, project_root=root, local=local, hroot=hroot)
    ev = mod.get("eval") or {}
    timeout = int(ev.get("timeout_seconds") or 300)
    max_retries = int(retries if retries is not None else ev.get("retries") or 2)

    last: dict[str, Any] = {}
    for attempt in range(max_retries + 1):
        try:
            if (mdir / "eval.py").exists():
                last = _run_module_eval_py(mdir, candidate_dir, baseline_dir, mod, timeout)
            else:
                cmd_t = ev.get("command")
                if not cmd_t:
                    last = {
                        "ok": False,
                        "error": "no eval.command and no module eval.py",
                        "metrics": {},
                        "gates_passed": False,
                        "reward_hack": False,
                        "reward_hack_reasons": [],
                    }
                    break
                cmd = cmd_t.format(
                    module=name,
                    candidate_dir=str(candidate_dir),
                    baseline_dir=str(baseline_dir or ""),
                    module_dir=str(mdir),
                    project_root=str(root),
                )
                proc = subprocess.run(
                    cmd,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    cwd=str(root),
                )
                if proc.returncode != 0:
                    last = {
                        "ok": False,
                        "error": f"eval command exit {proc.returncode}",
                        "stderr": proc.stderr[-4000:],
                        "metrics": {},
                        "gates_passed": False,
                        "reward_hack": False,
                        "reward_hack_reasons": [],
                    }
                else:
                    last = json.loads(proc.stdout.strip().splitlines()[-1])
            if last.get("ok"):
                break
        except subprocess.TimeoutExpired:
            last = {
                "ok": False,
                "error": "eval timeout",
                "metrics": {},
                "gates_passed": False,
                "reward_hack": False,
                "reward_hack_reasons": [],
            }
        except Exception as e:
            last = {
                "ok": False,
                "error": str(e),
                "metrics": {},
                "gates_passed": False,
                "reward_hack": False,
                "reward_hack_reasons": [],
            }
        if attempt < max_retries:
            time.sleep(0.2 * (attempt + 1))

    metrics = dict(last.get("metrics") or {})
    primary_name = (mod.get("metrics") or {}).get("primary")
    primary_val = metrics.get(primary_name) if primary_name else None

    hack_reasons = anti_reward_hack(mod, candidate_dir, root)
    if last.get("reward_hack_reasons"):
        hack_reasons = sorted(set(hack_reasons + list(last["reward_hack_reasons"])))
    reward_hack = bool(hack_reasons) or bool(last.get("reward_hack"))

    gates = apply_gates(mod, metrics) if metrics else False
    if last.get("gates_passed") is False:
        gates = False

    baseline_primary = None
    if baseline_dir and (baseline_dir / "scores.json").exists():
        try:
            b = json.loads((baseline_dir / "scores.json").read_text())
            baseline_primary = (b.get("metrics") or {}).get(primary_name)
        except Exception:
            pass

    cmp_ = compare_primary(mod, float(primary_val), float(baseline_primary)) if primary_val is not None and baseline_primary is not None else {}

    result = {
        "ok": bool(last.get("ok")) and not reward_hack and gates,
        "module": name,
        "metrics": metrics,
        "primary_metric": primary_name,
        "primary": primary_val,
        "baseline_primary": baseline_primary,
        "gates_passed": gates,
        "reward_hack": reward_hack,
        "reward_hack_reasons": hack_reasons,
        "compare": cmp_,
        "raw": last,
        "error": last.get("error"),
    }
    if reward_hack:
        result["ok"] = False
        result["error"] = "reward_hack: " + "; ".join(hack_reasons)
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Auto-optimizer eval harness")
    ap.add_argument("--module", default=None)
    ap.add_argument("--candidate-dir", type=Path, required=True)
    ap.add_argument("--baseline-dir", type=Path, default=None)
    ap.add_argument("--project-root", type=Path, default=None)
    ap.add_argument("--local", action="store_true")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--retries", type=int, default=None)
    args = ap.parse_args(argv)

    result = run_eval(
        module=args.module,
        candidate_dir=args.candidate_dir.resolve(),
        baseline_dir=args.baseline_dir.resolve() if args.baseline_dir else None,
        project_root=args.project_root.resolve() if args.project_root else None,
        local=args.local,
        retries=args.retries,
    )
    text = json.dumps(result, indent=2, default=str)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
