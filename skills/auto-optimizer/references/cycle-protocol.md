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
8. keep/revert
9. results.tsv + cycle report
10. On failure: failure_analysis → next_cycle_hints

## Subagent rules

- Orchestrator spawns all workers.
- Workers never spawn subagents (Grok depth limit).
- Persona: prepend instructions from `ao-*.toml`; tag description `[ao-stage]`.
