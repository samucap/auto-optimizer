#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPTS))

from workspace_init import init_workspace  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", action="store_true")
    ap.add_argument("--with-self-test", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--project-root", type=Path, default=None)
    args = ap.parse_args()
    hroot = init_workspace(
        local=args.local,
        project_root=args.project_root,
        with_self_test=args.with_self_test,
        force=args.force,
    )
    print(f"initialized harness at {hroot}")
    print(f"  modules: {hroot / 'modules'}")
    print(f"  active_module -> _template")
    print("  project .gitignore includes .grok/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
