#!/usr/bin/env bash
# Remove auto-optimizer symlinks from Grok discovery paths (~/.grok only).
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GROK_HOME="${GROK_HOME:-$HOME/.grok}"

rm_if_link() {
  local p="$1"
  if [[ -L "$p" ]]; then
    rm -f "$p"
    echo "removed $p"
  elif [[ -e "$p" ]]; then
    echo "skip (not a symlink): $p" >&2
  fi
}

rm_if_link "$GROK_HOME/skills/auto-optimizer"

shopt -s nullglob
for f in "$REPO"/personas/*.toml; do
  rm_if_link "$GROK_HOME/personas/$(basename "$f")"
done
for f in "$REPO"/roles/*.toml; do
  rm_if_link "$GROK_HOME/roles/$(basename "$f")"
done
for f in "$REPO"/agents/*.md; do
  rm_if_link "$GROK_HOME/agents/$(basename "$f")"
done
shopt -u nullglob

echo "auto-optimizer uninstall complete"
