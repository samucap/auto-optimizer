"""Bootstrap <project>/.grok/auto-optimizer/ workspace."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from paths import (
    harness_root,
    resolve_project_root,
    templates_dir,
)
from results_log import ensure_results_files
from state import default_state, save_state


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

# Ignore entire .grok directory in the *project* gitignore.
PROJECT_GITIGNORE_RULE = ".grok/"

_MODULE_NAME_RE = re.compile(r"^[a-zA-Z0-9]([a-zA-Z0-9_-]{0,62}[a-zA-Z0-9])?$")


def ensure_project_gitignore(project_root: Path) -> None:
    gi = project_root / ".gitignore"
    rule = PROJECT_GITIGNORE_RULE
    if gi.exists():
        text = gi.read_text(encoding="utf-8")
        lines = text.splitlines()
        if any(ln.strip() in {".grok/", ".grok", ".grok/**"} for ln in lines):
            return
        if text and not text.endswith("\n"):
            text += "\n"
        text += f"\n# Grok local config & auto-optimizer harness\n{rule}\n"
        gi.write_text(text, encoding="utf-8")
    else:
        gi.write_text(f"# Grok local config & auto-optimizer harness\n{rule}\n", encoding="utf-8")


def _copy_module_template(modules: Path, name: str, *, force: bool) -> Path:
    """Copy templates/modules/_template → modules/<name>."""
    if name in {"_template"}:
        raise ValueError("refusing to overwrite reserved module name via --module")
    if not _MODULE_NAME_RE.match(name):
        raise ValueError(
            f"invalid module name {name!r}: use 2–64 chars, letters/digits/hyphens/underscores, "
            "start and end with alphanumeric"
        )
    tmpl_src = templates_dir() / "modules" / "_template"
    if not tmpl_src.exists():
        raise FileNotFoundError(f"template missing: {tmpl_src}")
    dst = modules / name
    if dst.exists():
        if not force:
            raise FileExistsError(
                f"module already exists: {dst} (pass --force to replace)"
            )
        shutil.rmtree(dst)
    shutil.copytree(tmpl_src, dst)
    # Align module.yaml name field when present
    ypath = dst / "module.yaml"
    if ypath.exists():
        text = ypath.read_text(encoding="utf-8")
        if text.startswith("name:"):
            lines = text.splitlines()
            lines[0] = f"name: {name}"
            ypath.write_text("\n".join(lines) + ("\n" if text.endswith("\n") else ""), encoding="utf-8")
        else:
            # replace first name: line
            new_lines = []
            replaced = False
            for ln in text.splitlines():
                if not replaced and ln.startswith("name:"):
                    new_lines.append(f"name: {name}")
                    replaced = True
                else:
                    new_lines.append(ln)
            ypath.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    return dst


def init_workspace(
    *,
    local: bool = False,
    project_root: Path | None = None,
    with_self_test: bool = False,
    force: bool = False,
    module: str | None = None,
) -> Path:
    root = project_root or resolve_project_root(local=local)
    hroot = harness_root(root)
    hroot.mkdir(parents=True, exist_ok=True)

    (hroot / ".gitignore").write_text(HARNESS_GITIGNORE, encoding="utf-8")

    modules = hroot / "modules"
    modules.mkdir(exist_ok=True)
    experiments = hroot / "experiments"
    experiments.mkdir(exist_ok=True)
    (experiments / ".gitkeep").write_text("", encoding="utf-8")

    tmpl_src = templates_dir() / "modules" / "_template"
    tmpl_dst = modules / "_template"
    if tmpl_src.exists():
        if not tmpl_dst.exists():
            shutil.copytree(tmpl_src, tmpl_dst)
        elif force and module is None:
            # --force without --module: refresh stock _template
            shutil.rmtree(tmpl_dst)
            shutil.copytree(tmpl_src, tmpl_dst)

    if with_self_test:
        st_src = templates_dir() / "modules" / "self-test"
        st_dst = modules / "self-test"
        if st_src.exists() and (force or not st_dst.exists()):
            if st_dst.exists() and force:
                shutil.rmtree(st_dst)
            if not st_dst.exists():
                shutil.copytree(st_src, st_dst)

    active = "_template"
    if module:
        _copy_module_template(modules, module, force=force)
        active = module

    ensure_results_files(hroot)
    (hroot / "active_module").write_text(active + "\n", encoding="utf-8")

    st = default_state()
    st["status"] = "idle"
    st["module"] = active
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
