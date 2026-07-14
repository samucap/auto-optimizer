#!/usr/bin/env bash
# Install auto-optimizer into Grok discovery paths via symlinks.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GROK_HOME="${GROK_HOME:-$HOME/.grok}"

mkdir -p "$GROK_HOME/skills" "$GROK_HOME/personas" "$GROK_HOME/roles" "$GROK_HOME/agents"

ln -sfn "$REPO/skills/auto-optimizer" "$GROK_HOME/skills/auto-optimizer"

shopt -s nullglob
for f in "$REPO"/personas/*.toml; do
  ln -sfn "$f" "$GROK_HOME/personas/$(basename "$f")"
done
for f in "$REPO"/roles/*.toml; do
  ln -sfn "$f" "$GROK_HOME/roles/$(basename "$f")"
done
for f in "$REPO"/agents/*.md; do
  ln -sfn "$f" "$GROK_HOME/agents/$(basename "$f")"
done
shopt -u nullglob

mkdir -p "$HOME/.local/bin"
ln -sfn "$REPO/skills/auto-optimizer/bin/auto-optimizer" "$HOME/.local/bin/auto-optimizer"

echo "auto-optimizer installed from $REPO"
echo "  skill:    $GROK_HOME/skills/auto-optimizer"
echo "  CLI:      $HOME/.local/bin/auto-optimizer"
echo "  personas: $GROK_HOME/personas/ao-*.toml"
echo "Ensure ~/.local/bin is on PATH. Restart Grok TUI or wait for skill reload."
