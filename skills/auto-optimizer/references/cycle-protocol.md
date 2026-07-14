# Cycle protocol

## Workspace root

`<project>/.grok/auto-optimizer/`

## Artifact layout

```
experiments/<module>/<cycle_id>/
  module_snapshot.yaml
  01_research/{output.json,schema.json,summary.md}
  02_analysis/{...}
  03_architect/cN/{...}
  03_architect/winner.json
  04_review/{round_k.md,verdict.json}
  05_executor/cN/{sandbox/,scores.json,...}
  05_executor/winner.json
  06_final_review/
  cycle_report.json
  cycle_report.md
  errors.jsonl
```

## Pipeline

1. Load module + pending hints
2. Researcher (general-purpose + web) — not explore-only
3. Analyst
4. Architect tournament (parallel worktrees when live)
5. Reviewer (adversarial)
6. Executor tournament + eval oracle
7. Final reviewer
8. **Keep as proposal** (not auto-merge)
9. **cycle_report** + **results.tsv** (mandatory ledger)
10. On failure: failure_analysis → next_cycle_hints

## Keep = proposal (Karpathy-style)

Experiments are **proposals**, not deployments — similar to a DRL/eval pipeline that emits candidates for review:

| Outcome | Meaning |
|---------|---------|
| `kept: true` | Primary improved + gates (if required) → **git branch proposal** opened (`ao/<module>/<cycle_id>`) |
| `merged: false` | Default: **never** merges into the current branch |
| Main working tree / `HEAD` | Unchanged on branch keep (temp worktree only) |

Self-contained review files committed on the proposal branch (experiments under `.grok/` are often gitignored):

- `AO_KEEP.md` — metrics, findings, review/merge commands
- `AO_KEEP_SCORES.json` — machine-readable scores
- `AO_CYCLE/cycle_report.md` + `cycle_report.json` — cycle report snapshot
- `AO_CYCLE/errors.jsonl` — optional error log tail if present
- Winner file changes (module sandbox and/or project `files_to_edit`)

Also written under the cycle dir (local harness):

- `cycle_report.json` / `.md` — full scientific record (updated after keep with final `keep` meta)
- `keep.json` — branch, commit_sha, files, mode
- `results.tsv` / `results.jsonl` — longitudinal log

`state.json` is **loop control only** (active cycle, last_keep_* pointers). It is not the experiment archive.

```bash
git log -1 ao/<module>/<cycle_id>
git show ao/<module>/<cycle_id>:AO_KEEP.md
git show ao/<module>/<cycle_id>:AO_CYCLE/cycle_report.md
git merge ao/<module>/<cycle_id>   # only if you accept
```

## Subagent rules

- Orchestrator spawns all workers.
- Workers never spawn subagents (Grok depth limit).
- Persona: prepend instructions from `ao-*.toml`; tag description `[ao-stage]`.
