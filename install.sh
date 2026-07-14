#!/usr/bin/env bash
# Install auto-optimizer into Grok discovery paths only (~/.grok).
# Does not install a global CLI onto PATH.
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

echo "auto-optimizer installed from $REPO"
echo "  skill:    $GROK_HOME/skills/auto-optimizer"
echo "  personas: $GROK_HOME/personas/ao-*.toml"
echo "  roles:    $GROK_HOME/roles/ao-*.toml"
echo "  agents:   $GROK_HOME/agents/ao-*.md"
echo ""
echo "In Grok TUI:  /auto-optimizer"
echo "Shell runners (from this clone):"
echo "  export AO_HOME=\"$REPO\""
echo "  \"\$AO_HOME/skills/auto-optimizer/bin/auto-optimizer\" init --module <name>"
echo "  \"\$AO_HOME/skills/auto-optimizer/bin/start-loop.sh\" --module <name>"
echo "  \"\$AO_HOME/skills/auto-optimizer/scripts/acp-orchestrator.sh\" --once --module <name>"
echo "Restart Grok TUI or wait for skill reload."
