#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPTS))

from paths import harness_root, resolve_project_root, status_path  # noqa: E402
from state import load_state  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    root = resolve_project_root(local=args.local)
    hroot = harness_root(root)
    if not hroot.exists():
        print(f"not initialized: {hroot}", file=sys.stderr)
        return 1
    st = load_state(hroot)
    if args.json:
        print(json.dumps(st, indent=2))
    else:
        sp = status_path(hroot)
        if sp.exists():
            print(sp.read_text(encoding="utf-8"))
        else:
            print(json.dumps(st, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
