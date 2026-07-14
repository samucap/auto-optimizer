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
| This skill | `~/.grok/skills/auto-optimizer` (symlink to versioned `~/code/asians`) |
| Scripts | `<skill>/scripts/` (always via `uv run --with-requirements ...`) |
| Workspace harness | `<project>/.grok/auto-optimizer/` |
| Personas | `~/.grok/personas/ao-*.toml` |
| References | `<skill>/references/` |

## Invocation

Parse args from the user message: `--module`, `--once`, `--max-cycles`, `--local`, `--interval`, `--no-tmux`, `--dry-run`, `--live`, `--resume`.

### Prefer CLI when available

```bash
# Ensure workspace
auto-optimizer init [--local] [--with-self-test]

# Single offline-safe cycle (mock research stages + real module eval)
auto-optimizer once --module <name>

# Continuous background loop (tmux default)
auto-optimizer start --module <name> [--interval 5m] [--max-cycles N]

# Live multi-agent via grok CLI stages
auto-optimizer once --module <name> --live
# (pass through: the bin wrapper maps once → offline by default; for live use:)
uv run --with-requirements <skill>/scripts/requirements.txt \
  python <skill>/scripts/run_cycle.py --module <name> --live
```

If the user is in TUI and wants **native subagents**, you (this session) orchestrate with `spawn_subagent` as below instead of only shelling out.

## Step 0 — Workspace + module

1. Resolve project root (git root unless `--local`).
2. If `<root>/.grok/auto-optimizer` missing → run `auto-optimizer init`.
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

### 6. Keep / revert

- If primary improved (per direction) and secondary gates pass → apply winner changes into project (or module sandbox for template modules)
- Else leave tree unchanged
- Append results via cycle completion (or `results_log`)

### 7. Always write cycle report

Use `scripts/cycle_report.py` patterns: status, root_cause, failed_stages, partial_progress, scores, kept, recommendation.

### 8. On failure

Run failure analysis (`scripts/failure_analysis.py` logic): write `next_cycle_hints.md` + adjustments. Next cycle must consume them.

## Continuous loop

- For background: `auto-optimizer start` (tmux session `ao-<module>`).
- Or `/loop <interval> /auto-optimizer --module ... --once` in TUI.
- Stop: `auto-optimizer stop` or write `.grok/auto-optimizer/STOP`.

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
