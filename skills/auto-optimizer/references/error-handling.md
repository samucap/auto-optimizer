# Error handling

## Always

- Emit `cycle_report.json` + `.md` for every cycle (`success` | `failed` | `budget_exhausted`).
- Log structured events to `errors.jsonl`.
- On non-success: write `next_cycle_hints.md` + `next_cycle_adjustments.json`.

## Isolation

| Failure | Behavior |
|---------|----------|
| One tournament candidate dies | Continue with survivors |
| All candidates die | Stage fail → cycle report → adjust |
| Eval fail | Retry ≤2 then discard candidate |
| Schema fail | One retry with feedback (skill path); then discard |
| Reward hack | Immediate discard + log |
| Torn `state.json` | Load `state.json.prev` or re-init (atomic writes only) |

## State

Write via temp file + rename. Keep `.prev` last-good snapshot. No bit-rot mythology — only crash mid-write / interrupt.

## Loop

Default: continue after failure. `--stop-on-fail` to halt. `STOP` file ends loop cleanly.
