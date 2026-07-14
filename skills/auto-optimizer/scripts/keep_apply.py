"""Apply a winning candidate as a *proposal* (git branch) or inplace fallback.

Karpathy-style: experiments are proposals that may or may not be merged.
kept=true means a reviewable proposal was opened — not that main was updated.

Execute-plan-aligned git rules:
- Never switch the user's checked-out branch.
- Create branch from base_sha, apply via temp worktree, commit, remove worktree.
- No auto-merge in v1.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


def _run(
    args: list[str],
    *,
    cwd: Path | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        text=True,
        capture_output=True,
        check=check,
    )


def is_git_repo(project_root: Path) -> bool:
    try:
        r = _run(["git", "rev-parse", "--is-inside-work-tree"], cwd=project_root, check=False)
        return r.returncode == 0 and r.stdout.strip() == "true"
    except OSError:
        return False


def resolve_keep_mode(
    requested: str | None,
    *,
    project_root: Path,
    keep_policy: dict[str, Any] | None = None,
) -> str:
    """Return 'branch' or 'inplace'."""
    pol = keep_policy or {}
    mode = (requested or pol.get("mode") or "auto").strip().lower()
    if mode in ("branch", "inplace"):
        if mode == "branch" and not is_git_repo(project_root):
            return "inplace"
        return mode
    # auto
    return "branch" if is_git_repo(project_root) else "inplace"


def _slug(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9._-]+", "-", s.strip()).strip("-")
    return s[:80] or "module"


def keep_branch_name(module: str, cycle_id: str) -> str:
    return f"ao/{_slug(module)}/{_slug(cycle_id)}"


def _is_project_path(path: str) -> bool:
    """Heuristic: project-level paths vs module-local."""
    p = path.replace("\\", "/").lstrip("./")
    prefixes = (
        "config/",
        "src/",
        "internal/",
        "cmd/",
        "pkg/",
        "lib/",
        "app/",
        "services/",
        "deploy/",
    )
    return p.startswith(prefixes) or p.startswith(".grok/") is False and "/" in p and p.split("/")[0] in {
        "config",
        "src",
        "internal",
        "cmd",
        "pkg",
        "lib",
        "app",
        "services",
    }


def collect_apply_plan(
    *,
    project_root: Path,
    module: str,
    mdir: Path,
    candidate_dir: Path,
    files_to_edit: list[str] | None,
) -> list[tuple[Path, Path]]:
    """Return list of (src, dest_relative_to_project) pairs."""
    pairs: list[tuple[Path, Path]] = []
    edits = list(files_to_edit or [])

    def add(src: Path, dest_rel: Path) -> None:
        if src.is_file():
            pairs.append((src, dest_rel))

    if edits:
        for rel in edits:
            rel_n = rel.replace("\\", "/").lstrip("./")
            candidates = [
                candidate_dir / rel_n,
                candidate_dir / "sandbox" / Path(rel_n).name,
            ]
            # if path is like sandbox/score.py
            if not (candidate_dir / rel_n).exists() and rel_n.startswith("sandbox/"):
                candidates.insert(0, candidate_dir / rel_n)

            src = next((c for c in candidates if c.is_file()), None)
            if src is None:
                continue

            if rel_n.startswith("sandbox/") or not _looks_project_rooted(rel_n):
                # module-local under harness
                dest = (
                    Path(".grok")
                    / "auto-optimizer"
                    / "modules"
                    / module
                    / rel_n
                )
            else:
                dest = Path(rel_n)
            add(src, dest)
    else:
        # default: copy entire sandbox tree from candidate
        sandbox = candidate_dir / "sandbox"
        if sandbox.is_dir():
            for f in sandbox.rglob("*"):
                if f.is_file():
                    rel = f.relative_to(sandbox)
                    dest = (
                        Path(".grok")
                        / "auto-optimizer"
                        / "modules"
                        / module
                        / "sandbox"
                        / rel
                    )
                    add(f, dest)

    return pairs


def _looks_project_rooted(rel_n: str) -> bool:
    first = rel_n.split("/")[0]
    return first in {
        "config",
        "src",
        "internal",
        "cmd",
        "pkg",
        "lib",
        "app",
        "services",
        "deploy",
        "scripts",
    }


@dataclass
class KeepResult:
    mode: str
    kept: bool
    merged: bool = False
    branch: str | None = None
    base_sha: str | None = None
    commit_sha: str | None = None
    files: list[str] = field(default_factory=list)
    error: str | None = None
    review_commands: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def apply_inplace(
    *,
    project_root: Path,
    module: str,
    mdir: Path,
    candidate_dir: Path,
    files_to_edit: list[str] | None,
    dry_run: bool = False,
) -> KeepResult:
    pairs = collect_apply_plan(
        project_root=project_root,
        module=module,
        mdir=mdir,
        candidate_dir=candidate_dir,
        files_to_edit=files_to_edit,
    )
    if not pairs:
        # legacy: whole sandbox directory
        src = candidate_dir / "sandbox"
        dst = mdir / "sandbox"
        if src.is_dir() and not dry_run:
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
            return KeepResult(
                mode="inplace",
                kept=True,
                files=[str(Path(".grok") / "auto-optimizer" / "modules" / module / "sandbox")],
            )
        return KeepResult(mode="inplace", kept=False, error="no files to apply")

    applied: list[str] = []
    for src, dest_rel in pairs:
        dest = project_root / dest_rel
        applied.append(str(dest_rel))
        if dry_run:
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
    return KeepResult(mode="inplace", kept=True, files=applied)


def _write_keep_bundle(
    wt: Path,
    *,
    module: str,
    cycle_id: str,
    scores: dict[str, Any],
    experiment_path: str,
    recommendation: str | None,
    files: list[str],
    findings: str | None = None,
) -> None:
    scores_path = wt / "AO_KEEP_SCORES.json"
    scores_path.write_text(json.dumps(scores, indent=2, default=str) + "\n", encoding="utf-8")

    primary = scores.get("winner") or scores.get("primary")
    baseline = scores.get("baseline")
    lines = [
        f"# Auto-Optimizer keep proposal: `{module}` / `{cycle_id}`",
        "",
        "This branch is a **proposal** (Karpathy-style experiment). It is **not** merged into your current branch.",
        "Review metrics and diff, then merge only if you accept the change.",
        "",
        "## Metrics",
        "",
        f"- **primary (winner)**: `{primary}`",
        f"- **baseline**: `{baseline}`",
        f"- **experiment path (local)**: `{experiment_path}`",
        "",
        "## Files in this proposal",
        "",
    ]
    for f in files:
        lines.append(f"- `{f}`")
    lines.extend(["", "## Findings", "", findings or "(see cycle report / research artifacts on disk)", ""])
    if recommendation:
        lines.extend(["## Recommendation", "", recommendation, ""])
    lines.extend(
        [
            "## Review commands",
            "",
            "```bash",
            f"git log -1 ao/{_slug(module)}/{_slug(cycle_id)}",
            f"git show HEAD:AO_KEEP.md   # on this branch",
            f"git diff {scores.get('base_sha', 'HEAD~1') or 'HEAD~1'}...HEAD",
            f"# accept proposal:",
            f"git merge ao/{_slug(module)}/{_slug(cycle_id)}",
            "```",
            "",
        ]
    )
    (wt / "AO_KEEP.md").write_text("\n".join(lines), encoding="utf-8")


def apply_branch(
    *,
    project_root: Path,
    module: str,
    mdir: Path,
    candidate_dir: Path,
    cycle_id: str,
    files_to_edit: list[str] | None,
    scores: dict[str, Any],
    experiment_path: str,
    recommendation: str | None = None,
    findings: str | None = None,
    dry_run: bool = False,
) -> KeepResult:
    if not is_git_repo(project_root):
        return KeepResult(mode="branch", kept=False, error="not a git repository")

    pairs = collect_apply_plan(
        project_root=project_root,
        module=module,
        mdir=mdir,
        candidate_dir=candidate_dir,
        files_to_edit=files_to_edit,
    )
    if not pairs:
        return KeepResult(mode="branch", kept=False, error="no files to apply from candidate")

    try:
        base_sha = _run(["git", "rev-parse", "HEAD"], cwd=project_root).stdout.strip()
    except subprocess.CalledProcessError as e:
        return KeepResult(mode="branch", kept=False, error=f"rev-parse failed: {e.stderr}")

    branch = keep_branch_name(module, cycle_id)
    file_list = [str(d) for _, d in pairs]
    review_cmds = [
        f"git log -1 {branch}",
        f"git show {branch}:AO_KEEP.md",
        f"git diff {base_sha}...{branch}",
        f"git merge {branch}   # only if you accept the proposal",
    ]

    if dry_run:
        return KeepResult(
            mode="branch",
            kept=True,
            branch=branch,
            base_sha=base_sha,
            files=file_list,
            review_commands=review_cmds,
        )

    # If branch exists, fail clearly
    exists = _run(
        ["git", "rev-parse", "--verify", branch],
        cwd=project_root,
        check=False,
    )
    if exists.returncode == 0:
        return KeepResult(
            mode="branch",
            kept=False,
            branch=branch,
            base_sha=base_sha,
            error=f"branch already exists: {branch}",
        )

    wt_dir: Path | None = None
    try:
        _run(["git", "branch", branch, base_sha], cwd=project_root)
        wt_dir = Path(tempfile.mkdtemp(prefix="ao-keep-wt-"))
        wt_dir.rmdir()
        # Checks out `branch` in an isolated worktree — does not move main checkout
        _run(
            ["git", "worktree", "add", str(wt_dir), branch],
            cwd=project_root,
        )

        for src, dest_rel in pairs:
            dest = wt_dir / dest_rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)

        scores_with_base = dict(scores)
        scores_with_base["base_sha"] = base_sha
        scores_with_base["branch"] = branch
        scores_with_base["merged"] = False
        _write_keep_bundle(
            wt_dir,
            module=module,
            cycle_id=cycle_id,
            scores=scores_with_base,
            experiment_path=experiment_path,
            recommendation=recommendation,
            files=file_list,
            findings=findings,
        )

        # Force-add: harness paths under .grok/ are often gitignored but must ship on the proposal branch
        _run(["git", "add", "-f", "AO_KEEP.md", "AO_KEEP_SCORES.json"], cwd=wt_dir)
        for _, dest_rel in pairs:
            _run(["git", "add", "-f", "--", str(dest_rel)], cwd=wt_dir)

        msg = (
            f"ao(keep): proposal {module} {cycle_id}\n\n"
            f"Proposal only — not merged. Review AO_KEEP.md and metrics.\n"
            f"primary={scores.get('winner')} baseline={scores.get('baseline')}\n"
        )
        env_commit = os.environ.copy()
        env_commit.setdefault("GIT_AUTHOR_NAME", "auto-optimizer")
        env_commit.setdefault("GIT_AUTHOR_EMAIL", "auto-optimizer@localhost")
        env_commit.setdefault("GIT_COMMITTER_NAME", "auto-optimizer")
        env_commit.setdefault("GIT_COMMITTER_EMAIL", "auto-optimizer@localhost")
        subprocess.run(
            ["git", "commit", "-m", msg],
            cwd=str(wt_dir),
            text=True,
            capture_output=True,
            check=True,
            env=env_commit,
        )
        commit_sha = _run(["git", "rev-parse", "HEAD"], cwd=wt_dir).stdout.strip()

        return KeepResult(
            mode="branch",
            kept=True,
            merged=False,
            branch=branch,
            base_sha=base_sha,
            commit_sha=commit_sha,
            files=file_list,
            review_commands=review_cmds,
        )
    except subprocess.CalledProcessError as e:
        err = (e.stderr or e.stdout or str(e)).strip()
        # best-effort cleanup of branch if commit failed mid-way
        return KeepResult(
            mode="branch",
            kept=False,
            branch=branch,
            base_sha=base_sha,
            error=err or "git keep failed",
        )
    finally:
        if wt_dir is not None:
            _run(
                ["git", "worktree", "remove", "--force", str(wt_dir)],
                cwd=project_root,
                check=False,
            )
            if wt_dir.exists():
                shutil.rmtree(wt_dir, ignore_errors=True)


def apply_keep(
    *,
    project_root: Path,
    module: str,
    mdir: Path,
    candidate_dir: Path,
    cycle_id: str,
    mod: dict[str, Any],
    scores: dict[str, Any],
    experiment_path: str,
    recommendation: str | None = None,
    findings: str | None = None,
    dry_run: bool = False,
    keep_mode: str | None = None,
) -> KeepResult:
    mode = resolve_keep_mode(
        keep_mode,
        project_root=project_root,
        keep_policy=mod.get("keep_policy") or {},
    )
    files_to_edit = mod.get("files_to_edit")
    if isinstance(files_to_edit, str):
        files_to_edit = [files_to_edit]
    if mode == "branch":
        return apply_branch(
            project_root=project_root,
            module=module,
            mdir=mdir,
            candidate_dir=candidate_dir,
            cycle_id=cycle_id,
            files_to_edit=files_to_edit,
            scores=scores,
            experiment_path=experiment_path,
            recommendation=recommendation,
            findings=findings,
            dry_run=dry_run,
        )
    return apply_inplace(
        project_root=project_root,
        module=module,
        mdir=mdir,
        candidate_dir=candidate_dir,
        files_to_edit=files_to_edit,
        dry_run=dry_run,
    )
