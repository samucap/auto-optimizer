#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPTS))

from workspace_init import init_workspace  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Initialize .grok/auto-optimizer harness")
    ap.add_argument("--local", action="store_true")
    ap.add_argument("--with-self-test", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument(
        "--module",
        default=None,
        help="Create modules/<name> from _template and set active_module",
    )
    ap.add_argument("--project-root", type=Path, default=None)
    args = ap.parse_args()
    try:
        hroot = init_workspace(
            local=args.local,
            project_root=args.project_root,
            with_self_test=args.with_self_test,
            force=args.force,
            module=args.module,
        )
    except (FileExistsError, ValueError, FileNotFoundError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    active = (hroot / "active_module").read_text(encoding="utf-8").strip()
    print(f"initialized harness at {hroot}")
    print(f"  modules: {hroot / 'modules'}")
    print(f"  active_module -> {active}")
    if args.module:
        print(f"  created module: {hroot / 'modules' / args.module}")
        print(f"  edit: {hroot / 'modules' / args.module / 'module.yaml'}")
    print("  project .gitignore includes .grok/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
