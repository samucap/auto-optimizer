"""Bootstrap <project>/.grok/auto-optimizer/ workspace."""

from __future__ import annotations

import shutil
from pathlib import Path

from paths import (
    harness_root,
    resolve_project_root,
    results_tsv_path,
    skill_root,
    templates_dir,
)
from results_log import TSV_HEADER, ensure_results_files
from state import atomic_write_text, default_state, save_state


HARNESS_GITIGNORE = """# Auto-optimizer harness (runtime)
experiments/
state.json
state.json.prev
STATUS.md
STATUS.md.prev
results.tsv
results.jsonl
*.log
next_cycle_hints.md
next_cycle_adjustments.json
STOP
"""

# Per plan review: ignore entire .grok directory in the *project* gitignore.
PROJECT_GITIGNORE_RULE = ".grok/"


def ensure_project_gitignore(project_root: Path) -> None:
    gi = project_root / ".gitignore"
    rule = PROJECT_GITIGNORE_RULE
    if gi.exists():
        text = gi.read_text(encoding="utf-8")
        lines = text.splitlines()
        # already covered?
        if any(ln.strip() in {".grok/", ".grok", ".grok/**"} for ln in lines):
            return
        if text and not text.endswith("\n"):
            text += "\n"
        text += f"\n# Grok local config & auto-optimizer harness\n{rule}\n"
        gi.write_text(text, encoding="utf-8")
    else:
        gi.write_text(f"# Grok local config & auto-optimizer harness\n{rule}\n", encoding="utf-8")


def init_workspace(
    *,
    local: bool = False,
    project_root: Path | None = None,
    with_self_test: bool = False,
    force: bool = False,
) -> Path:
    root = project_root or resolve_project_root(local=local)
    hroot = harness_root(root)
    hroot.mkdir(parents=True, exist_ok=True)

    # harness-local gitignore (in case someone force-adds .grok)
    (hroot / ".gitignore").write_text(HARNESS_GITIGNORE, encoding="utf-8")

    modules = hroot / "modules"
    modules.mkdir(exist_ok=True)
    experiments = hroot / "experiments"
    experiments.mkdir(exist_ok=True)
    (experiments / ".gitkeep").write_text("", encoding="utf-8")

    tmpl_src = templates_dir() / "modules" / "_template"
    tmpl_dst = modules / "_template"
    if tmpl_src.exists() and (force or not tmpl_dst.exists()):
        if tmpl_dst.exists() and force:
            shutil.rmtree(tmpl_dst)
        if not tmpl_dst.exists():
            shutil.copytree(tmpl_src, tmpl_dst)

    if with_self_test:
        st_src = templates_dir() / "modules" / "self-test"
        st_dst = modules / "self-test"
        if st_src.exists() and (force or not st_dst.exists()):
            if st_dst.exists() and force:
                shutil.rmtree(st_dst)
            if not st_dst.exists():
                shutil.copytree(st_src, st_dst)

    ensure_results_files(hroot)
    if not (hroot / "active_module").exists():
        (hroot / "active_module").write_text("_template\n", encoding="utf-8")

    st = default_state()
    st["status"] = "idle"
    st["module"] = "_template"
    save_state(hroot, st)

    ensure_project_gitignore(root)

    readme = hroot / "README.md"
    if not readme.exists():
        readme.write_text(
            "# Auto-Optimizer workspace\n\n"
            "Harness data for `/auto-optimizer`. Modules live in `modules/`.\n"
            "This entire `.grok/` tree is intended to be gitignored at the project root.\n",
            encoding="utf-8",
        )

    return hroot
