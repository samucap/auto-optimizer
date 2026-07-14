---
name: auto-optimizer
description: >
  Background multi-subagent auto-optimization loop: load workspace module under
  .grok/auto-optimizer/, run Researcher→Analyst→Architect tournament→Reviewer→
  Executor tournament, eval, optional keep, log results; on failure analyze and
  adjust for the next cycle.
when-to-use: >
  Use when the user runs /auto-optimizer, or asks for auto-optimizer, auto optimize,
  continuous improvement loop, modular research cycle, karpathy-style research loop.
argument-hint: "[--module NAME] [--once] [--max-cycles N] [--local] [--interval DUR] [--no-tmux] [--dry-run] [--resume] [--live]"
---

# Auto-Optimizer Skill

You are the **orchestrator** for a modular Karpathy-style optimization loop native to Grok Build.

## Paths

| What | Where |
|------|--------|
| This skill | `~/.grok/skills/auto-optimizer` (symlink to this repo’s `skills/auto-optimizer`) |
| Scripts | `<skill>/scripts/` (always via `uv run --with-requirements ...`) |
| Workspace harness | `<project>/.grok/auto-optimizer/` |
| Personas | `~/.grok/personas/ao-*.toml` |
| Clone / AO_HOME | Path to this repository (set `AO_HOME` or use absolute skill path) |
| References | `<skill>/references/` |

## Invocation

Parse args from the user message: `--module`, `--once`, `--max-cycles`, `--local`, `--interval`, `--no-tmux`, `--dry-run`, `--live`, `--resume`.

### Prefer shell entrypoints from the clone when needed

```bash
export AO_HOME=<path-to-this-repo>   # clone of the auto-optimizer repo

# Ensure workspace + create a named module from template
"$AO_HOME/skills/auto-optimizer/bin/auto-optimizer" init --module <name>

# Single offline-safe cycle (mock research stages + real module eval)
"$AO_HOME/skills/auto-optimizer/bin/auto-optimizer" once --module <name>

# Continuous background loop (tmux default)
"$AO_HOME/skills/auto-optimizer/bin/start-loop.sh" --module <name> [--interval 5m] [--max-cycles N]

# Script orchestrator
"$AO_HOME/skills/auto-optimizer/scripts/acp-orchestrator.sh" --once --module <name>
"$AO_HOME/skills/auto-optimizer/scripts/acp-orchestrator.sh" --once --module <name> --live
```

If the user is in TUI and wants **native subagents**, you (this session) orchestrate with `spawn_subagent` as below instead of only shelling out.

## Step 0 — Workspace + module

1. Resolve project root (git root unless `--local`).
2. If `<root>/.grok/auto-optimizer` missing → run `…/bin/auto-optimizer init [--module NAME]`.
3. Load module: `uv run ... scripts/load_module.py --module ...` or read `modules/<name>/module.yaml`.
4. Read `next_cycle_hints.md` if present; inject into Researcher/Analyst.
5. Create `experiments/<module>/<cycle_id>/` (cycle_id via `python -c` uuid/time).
6. Read persona instructions from `~/.grok/personas/ao-*.toml` (extract `instructions`).

## Step 1 — Multi-subagent pipeline (you spawn all workers)

**Depth limit:** only you spawn. Workers must not spawn children. Tag descriptions `[ao-researcher]`, etc.

### 1. Researcher (required; NOT explore-only)

- `subagent_type`: `general-purpose`
- `capability_mode`: `all` (needs web)
- Prepend **ao-researcher** persona
- Prompt: full module.yaml, local seeds, hints; require web research with official docs when `stages.researcher.web` is true
- Artifacts: `01_research/output.json` + `schema.json` + `summary.md`
- Validate with `scripts/validate_output.py`; one retry with feedback; then fail stage

### 2. Analyst

- Same pattern → `02_analysis/`
- Persona **ao-analyst**

### 3. Architect tournament (3–5 parallel)

- `background: true`, `isolation: worktree`
- Persona **ao-architect**
- N from `module.stages.architect.candidates` / budgets
- On failures: continue with survivors
- Rank / pick winner → `03_architect/winner.json`

### 4. Reviewer (adversarial, iterative)

- Persona **ao-reviewer**
- Max rounds: `budgets.max_reviewer_iterations`
- Verdicts: approve | revise_architecture | revise_execution | reject
- On budget exhaust: cycle status `budget_exhausted`, still write full report

### 5. Executor tournament (2–4 parallel worktrees)

- Persona **ao-executor**
- Implement only `files_to_edit`
- Eval each candidate:
  ```bash
  uv run --with-requirements <skill>/scripts/requirements.txt \
    python <skill>/scripts/eval.py --module <name> --candidate-dir <path>
  ```
- Discard reward_hack; pick best by metrics.direction
- Final **ao-reviewer** pass on winner

### 6. Keep = proposal branch (not auto-merge)

Karpathy-style / DRL-eval pipeline: if primary improved and secondary gates pass → open a **reviewable git proposal**, do **not** merge into the user’s current branch.

Protocol (execute-plan-aligned; never checkout-switch or commit on the main workspace):

1. Write local `cycle_report` + decide keep (ledger first).
2. `git branch ao/<module>/<cycle_id> <base_sha>`
3. `git worktree add <tmp> ao/<module>/<cycle_id>` (isolated; does not move `HEAD`)
4. Apply winner files; commit on the **worktree only**:
   - changed files (`git add -f` if under gitignored `.grok/`)
   - `AO_KEEP.md` + `AO_KEEP_SCORES.json`
   - `AO_CYCLE/cycle_report.{json,md}` (+ `AO_CYCLE/errors.jsonl` if present)
5. Remove worktree; write `experiments/.../keep.json`; set `last_keep_*` in state
6. `kept: true` means **proposal opened**; `merged: false` — never auto-merge

If not a git repo, fallback inplace copy (`keep_policy.mode` / `--keep-mode`).

**Git safety:** auto-optimizer never commits skill development onto the user’s current branch. Only `ao/*` proposal branches (temp worktree). Unsolicited commits on `main` from a TUI coding agent are unrelated and must not happen without user approval.

### 7. Always write cycle report + results_log

Mandatory every cycle: `cycle_report.json`/`.md` and append `results.tsv`/`results.jsonl`.  
`state.json` is loop control only (pointers like `last_keep_branch`), not the science ledger.

### 8. On failure

Run failure analysis (`scripts/failure_analysis.py` logic): write `next_cycle_hints.md` + adjustments. Next cycle must consume them.

## Continuous loop

- For background: `$AO_HOME/skills/auto-optimizer/bin/start-loop.sh` (tmux session `ao-<module>`).
- Or `/loop <interval> /auto-optimizer --module ... --once` in TUI.
- Stop: `…/bin/auto-optimizer stop` or write `.grok/auto-optimizer/STOP`.

## Hard rules

1. Never hardcode research topics — only `module.yaml`.
2. Never use the `openai` package; LLM judges use `xai-sdk` only.
3. Python only via `uv run --with-requirements <skill>/scripts/requirements.txt`.
4. Workers: do not spawn subagents.
5. Anti-reward-hack: discard immediately on harness mutation / test deletion / hardcoded metrics.
6. Project `.gitignore` should ignore entire `.grok/` (init does this).

## References

- `references/module-schema.md`
- `references/cycle-protocol.md`
- `references/error-handling.md`
