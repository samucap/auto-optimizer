# module.yaml reference

Single source of truth for a workspace module under:

`.grok/auto-optimizer/modules/<name>/module.yaml`

## Required fields

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Module id (prefer match directory name) |
| `topic` | string | Research/optimization topic |
| `goal` | string | Success criteria in prose |
| `metrics.primary` | string | Primary metric name |
| `metrics.direction` | `minimize` \| `maximize` | Optimization direction |
| `eval` | mapping | Eval config (`timeout_seconds`, `retries`, optional `command`) |

## Common optional fields

- `objective_type`: `research` \| `design` \| `code_improvement` \| `custom`
- `deliverables`, `files_to_edit`, `files_forbidden`
- `metrics.secondary[]` with `name`, `direction`, `min_value` / `max_value`
- `budgets`: `max_cycles`, `max_reviewer_iterations`, `max_architect_candidates`, `max_executor_candidates`, `max_wall_time_minutes`
- `stages.<name>`: `enabled`, `candidates`, researcher `web` / `min_sources`
- `sources[]`, `source_paths[]` — seeds for Researcher
- `anti_reward_hacking.forbid_edit_globs`, `detect`
- `keep_policy`:
  - `mode`: `auto` \| `branch` \| `inplace` — `auto` uses git proposal branch when the project is a git repo, else inplace copy
  - `require_primary_improved` (default true) — no proposal unless primary beats baseline
  - `require_secondary_gates` (default true) — no proposal unless eval `gates_passed`
  - `on_tie`: `keep_baseline` (reserved; ties do not open a proposal when require_primary_improved)

## Module-local eval

If `modules/<name>/eval.py` exists, the harness runs it with:

```bash
python eval.py --candidate-dir <path> [--baseline-dir <path>]
```

Stdout must be JSON including `ok`, `metrics`, `gates_passed`, `reward_hack`, `reward_hack_reasons`.
