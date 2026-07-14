# Auto-Optimizer

Production-grade, module-swappable **Karpathy-style auto-optimization** loop native to Grok Build.

This repository is the **versioned source of truth**. `./install.sh` registers the skill with Grok under `~/.grok` only (no global CLI on your `PATH`).

In the examples below:

- `<repo-root>` — wherever you cloned **this** repository  
- `$AO_HOME` — optional convenience: `export AO_HOME=<repo-root>`  
- Target project — the codebase you want to optimize (may be a different directory)

---

## Install (Grok discovery only)

```bash
cd <repo-root>
./install.sh
```

This symlinks into:

| Link | Target |
|------|--------|
| `~/.grok/skills/auto-optimizer` | `<repo-root>/skills/auto-optimizer` |
| `~/.grok/personas/ao-*.toml` | `<repo-root>/personas/...` |
| `~/.grok/roles/ao-*.toml` | `<repo-root>/roles/...` |
| `~/.grok/agents/ao-*.md` | `<repo-root>/agents/...` |

Then in Grok TUI (any project):

```text
/auto-optimizer
/auto-optimizer --module my-first-goal
```

Uninstall Grok links: `./uninstall.sh`

---

## Configure a module

Harness state lives under the **target project**, not in this repo:

```text
<your-project>/.grok/auto-optimizer/
  modules/<name>/module.yaml
  experiments/
  active_module
  results.tsv
  ...
```

`init` adds `.grok/` to the project’s `.gitignore` so harness data stays out of product history.

### One-step module create

```bash
cd /path/to/your-project
export AO_HOME=<repo-root>

"$AO_HOME/skills/auto-optimizer/bin/auto-optimizer" init --module my-first-goal
```

That:

1. Creates `.grok/auto-optimizer/`
2. Copies the built-in `_template` module (kept as a clean source)
3. Creates `modules/my-first-goal` from that template
4. Sets `active_module` to `my-first-goal`

Then edit:

```text
.grok/auto-optimizer/modules/my-first-goal/module.yaml
```

### Important `module.yaml` fields

| Field | Purpose |
|-------|---------|
| `topic` / `goal` | What to research and optimize |
| `metrics.primary` / `metrics.direction` | `minimize` or `maximize` the primary score |
| `metrics.secondary` | Hard gates (e.g. `correctness >= 1.0`) |
| `files_to_edit` / `files_forbidden` | What executors may touch |
| `budgets` | Cycles, reviewer rounds, tournament sizes |
| `stages` | Enable stages; researcher `web`, candidate counts |
| `eval` | Timeouts/retries; optional command (or use module-local `eval.py`) |
| `sources` / `source_paths` | Seeds for the Researcher |
| `keep_policy` | When to open a keep **proposal** (`mode`, primary/gates); never auto-merges |

Optional: module-local `eval.py` next to `module.yaml` (see `_template`).

Use `_template` as-is only for smoke tests; prefer `init --module <name>` for real goals.

---

## Run from the shell

Shell entrypoints live **in this clone**. Set `AO_HOME` once per shell (or use relative paths from `<repo-root>`).

### Continuous loop — `start-loop.sh`

tmux session by default (`ao-<module>`). Cwd should be the **target project**.

```bash
cd /path/to/your-project
export AO_HOME=<repo-root>

"$AO_HOME/skills/auto-optimizer/bin/start-loop.sh" --module my-first-goal

# useful flags
"$AO_HOME/skills/auto-optimizer/bin/start-loop.sh" --module my-first-goal --max-cycles 5
"$AO_HOME/skills/auto-optimizer/bin/start-loop.sh" --module my-first-goal --interval 5m
"$AO_HOME/skills/auto-optimizer/bin/start-loop.sh" --module my-first-goal --no-tmux
"$AO_HOME/skills/auto-optimizer/bin/start-loop.sh" --module my-first-goal --live
"$AO_HOME/skills/auto-optimizer/bin/start-loop.sh" --module my-first-goal --stop-on-fail
```

| Flag | Meaning |
|------|---------|
| `--module NAME` | Module under `.grok/auto-optimizer/modules/` |
| `--max-cycles N` | Stop after N cycles |
| `--interval DUR` | Sleep between cycles (`60s`, `5m`, `1h`) |
| `--no-tmux` | Foreground loop (also used if tmux is missing) |
| `--live` | Use `grok -p` for agent stages (needs `grok` CLI) |
| `--local` | Harness under CWD, not git root |
| `--stop-on-fail` | Exit loop on first non-success cycle |

Stop a running loop:

```bash
"$AO_HOME/skills/auto-optimizer/bin/auto-optimizer" stop
# or attach: tmux attach -t ao-my-first-goal
```

### Script orchestrator — `acp-orchestrator.sh`

Python cycle driver (via `uv`). Prefer this for one-shot or scripted automation.

```bash
cd /path/to/your-project
export AO_HOME=<repo-root>

# single cycle (offline-safe research mocks + real module eval by default)
"$AO_HOME/skills/auto-optimizer/scripts/acp-orchestrator.sh" \
  --once --module my-first-goal

# several cycles with pause
"$AO_HOME/skills/auto-optimizer/scripts/acp-orchestrator.sh" \
  --module my-first-goal --max-cycles 10 --interval 5m

# live headless Grok stages
"$AO_HOME/skills/auto-optimizer/scripts/acp-orchestrator.sh" \
  --once --module my-first-goal --live
```

### In-repo CLI helpers

Same tree as `start-loop.sh` (not installed to `PATH`):

```bash
"$AO_HOME/skills/auto-optimizer/bin/auto-optimizer" once --module my-first-goal
"$AO_HOME/skills/auto-optimizer/bin/auto-optimizer" status
"$AO_HOME/skills/auto-optimizer/bin/auto-optimizer" stop
```

---

## Reviewing a keep proposal

When eval says a candidate improved the primary metric, auto-optimizer opens a **git proposal branch** — it does **not** merge into your current branch (Karpathy-style: experiment → measure → propose → human may implement).

```bash
# after a successful cycle with kept=true
git branch --list 'ao/*'
git log -1 ao/<module>/<cycle_id>
git show ao/<module>/<cycle_id>:AO_KEEP.md
git show ao/<module>/<cycle_id>:AO_KEEP_SCORES.json
git show ao/<module>/<cycle_id>:AO_CYCLE/cycle_report.md

# accept the proposal only if you want it in the codebase
git merge ao/<module>/<cycle_id>
```

Also always check the harness ledger:

- `.grok/auto-optimizer/experiments/<module>/<cycle_id>/cycle_report.md`
- `.grok/auto-optimizer/experiments/<module>/<cycle_id>/keep.json`
- `.grok/auto-optimizer/results.tsv`

`kept=true` means **proposal opened**, not **shipped to production**. Your current branch `HEAD` does not move; only `ao/*` branches receive commits (via a temporary worktree).

---

## Self-test

What it does: an **offline** integration suite in a **temporary directory** (no Grok TUI; no API key required for the default path).

```bash
export AO_HOME=<repo-root>
"$AO_HOME/skills/auto-optimizer/bin/auto-optimizer" self-test
```

Checks:

1. `init` creates harness under `.grok/auto-optimizer/` and adds `.grok/` to `.gitignore`
2. **Success** cycle on `_template` (mock research stages + real eval; proposal branch keep + `AO_CYCLE`)
3. **Schema** failure → `failed` cycle report + `next_cycle_hints`
4. **Eval** failure → failed report
5. **Reward-hack** discard path
6. **`budget_exhausted`** status path
7. **Module switch** back to `_template`
8. `results.tsv` / `results.jsonl` were written

Exits `0` only if all assertions pass. `--live` is optional manual smoke (not a full automated multi-agent suite).

---

## Layout

| Path | Role |
|------|------|
| `skills/auto-optimizer/` | Skill (`SKILL.md`), scripts, bin runners, module templates |
| `personas/`, `roles/`, `agents/` | Grok defs (`ao-*`) |
| `install.sh` / `uninstall.sh` | Symlink into / out of `~/.grok` only |
| Target project `.grok/auto-optimizer/` | Modules, experiments, state (created by `init`) |

---

## Requirements

- [uv](https://docs.astral.sh/uv/) (Python entrypoints)
- `tmux` recommended for continuous loops (`--no-tmux` if unavailable)
- `grok` CLI for `--live` headless stages and TUI skill use
- Optional: `XAI_API_KEY` when using xai-sdk judges

---

## License

Apache-2.0 (or project default)
