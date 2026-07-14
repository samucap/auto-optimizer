#!/usr/bin/env python3
"""Module-local eval for _template: sum score(n) over fixtures; correctness gate."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path


def load_score_fn(candidate_dir: Path):
    path = candidate_dir / "sandbox" / "score.py"
    if not path.exists():
        # allow candidate_dir itself to be the sandbox root
        path = candidate_dir / "score.py"
    if not path.exists():
        raise FileNotFoundError(f"score.py not found under {candidate_dir}")
    spec = importlib.util.spec_from_file_location("ao_score", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if not hasattr(mod, "score"):
        raise AttributeError("score.py must define score(n)")
    return mod.score


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidate-dir", type=Path, required=True)
    ap.add_argument("--baseline-dir", type=Path, default=None)
    args = ap.parse_args()

    module_dir = Path(__file__).resolve().parent
    cases_path = module_dir / "fixtures" / "cases.json"
    cases = json.loads(cases_path.read_text(encoding="utf-8"))["cases"]

    try:
        score_fn = load_score_fn(args.candidate_dir.resolve())
    except Exception as e:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": str(e),
                    "metrics": {},
                    "gates_passed": False,
                    "reward_hack": False,
                    "reward_hack_reasons": [],
                }
            )
        )
        return 1

    total = 0
    correctness = 1.0
    for c in cases:
        n = int(c["n"])
        try:
            v = score_fn(n)
            if not isinstance(v, (int, float)):
                correctness = 0.0
                break
            total += float(v)
        except Exception:
            correctness = 0.0
            break

    metrics = {"score_sum": total, "correctness": correctness}
    ok = correctness >= 1.0
    print(
        json.dumps(
            {
                "ok": ok,
                "metrics": metrics,
                "gates_passed": ok,
                "reward_hack": False,
                "reward_hack_reasons": [],
            }
        )
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
