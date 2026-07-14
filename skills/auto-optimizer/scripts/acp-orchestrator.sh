#!/usr/bin/env bash
# Thin Bash wrapper → uv run acp-orchestrator.py
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REQ="$DIR/requirements.txt"
if ! command -v uv >/dev/null 2>&1; then
  echo "uv required" >&2
  exit 1
fi
exec uv run --with-requirements "$REQ" python "$DIR/acp-orchestrator.py" "$@"
