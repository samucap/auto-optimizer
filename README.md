# Auto-Optimizer

Production-grade, module-swappable **Karpathy-style auto-optimization** loop native to [Grok Build](https://x.ai).

Versioned source of truth lives **here** (`~/code/asians`). Grok discovers the skill via symlinks created by `./install.sh` into `~/.grok/`.

## Quick start

```bash
# 1. Install into Grok discovery paths
./install.sh

# 2. In any project you want to optimize
cd /path/to/your/project
auto-optimizer init
cp -r .grok/auto-optimizer/modules/_template \
      .grok/auto-optimizer/modules/my-first-goal
# edit .grok/auto-optimizer/modules/my-first-goal/module.yaml

# 3. Run (tmux background loop by default)
auto-optimizer start --module my-first-goal

# or a single cycle
auto-optimizer once --module my-first-goal

# or in Grok TUI
# /auto-optimizer --module my-first-goal
```

## Layout

| Path | Role |
|------|------|
| `skills/auto-optimizer/` | Skill, scripts, CLI, module templates |
| `personas/`, `roles/`, `agents/` | Grok personas / roles / agent defs (`ao-*`) |
| `install.sh` | Symlink into `~/.grok` + `~/.local/bin` |
| Per-project `.grok/auto-optimizer/` | Modules, experiments, state (created by `init`) |

Project `init` adds `.grok/` to the project's `.gitignore` so harness state never pollutes product history.

## Requirements

- [uv](https://docs.astral.sh/uv/) (Python entrypoints)
- `tmux` (default continuous loop; use `--no-tmux` if missing)
- `grok` CLI for live multi-subagent cycles
- Optional: `XAI_API_KEY` for xai-sdk LLM judges

## Self-test

```bash
./install.sh
auto-optimizer self-test
```

## License

Apache-2.0 (or project default)
