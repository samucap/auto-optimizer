#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPTS))

from paths import harness_root, resolve_project_root, stop_file_path  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", action="store_true")
    args = ap.parse_args()
    root = resolve_project_root(local=args.local)
    hroot = harness_root(root)
    hroot.mkdir(parents=True, exist_ok=True)
    stop_file_path(hroot).write_text("stop\n", encoding="utf-8")
    print(f"wrote {stop_file_path(hroot)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
