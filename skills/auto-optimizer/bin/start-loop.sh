#!/usr/bin/env bash
# Continuous auto-optimizer loop. tmux by default.
set -euo pipefail

_SOURCE="${BASH_SOURCE[0]}"
while [[ -L "$_SOURCE" ]]; do
  _DIR="$(cd "$(dirname "$_SOURCE")" && pwd)"
  _SOURCE="$(readlink "$_SOURCE")"
  [[ "$_SOURCE" != /* ]] && _SOURCE="$_DIR/$_SOURCE"
done
BIN_DIR="$(cd "$(dirname "$_SOURCE")" && pwd)"
SKILL_DIR="$(cd "$BIN_DIR/.." && pwd)"
SCRIPTS="$SKILL_DIR/scripts"
REQ="$SCRIPTS/requirements.txt"

MODULE=""
MAX_CYCLES=""
INTERVAL="0"
NO_TMUX=0
LOCAL=0
LIVE=0
STOP_ON_FAIL=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --module) MODULE="${2:-}"; shift 2 ;;
    --max-cycles) MAX_CYCLES="${2:-}"; shift 2 ;;
    --interval) INTERVAL="${2:-}"; shift 2 ;;
    --no-tmux) NO_TMUX=1; shift ;;
    --local) LOCAL=1; shift ;;
    --live) LIVE=1; shift ;;
    --stop-on-fail) STOP_ON_FAIL=1; shift ;;
    -h|--help)
      echo "Usage: start-loop.sh [--module NAME] [--max-cycles N] [--interval DUR] [--no-tmux] [--local] [--live] [--stop-on-fail]"
      exit 0
      ;;
    *) echo "unknown arg: $1" >&2; exit 1 ;;
  esac
done

if ! command -v uv >/dev/null 2>&1; then
  echo "uv required" >&2
  exit 1
fi

# Resolve harness for session naming / logging via python one-liner
PROJECT_ROOT="$(pwd)"
if [[ $LOCAL -eq 0 ]] && git rev-parse --show-toplevel >/dev/null 2>&1; then
  PROJECT_ROOT="$(git rev-parse --show-toplevel)"
fi
HARNESS="$PROJECT_ROOT/.grok/auto-optimizer"
mkdir -p "$HARNESS"
if [[ -n "$MODULE" ]]; then
  echo "$MODULE" > "$HARNESS/active_module"
fi
MOD_NAME="$(tr -c 'A-Za-z0-9_-' '_' < "$HARNESS/active_module" 2>/dev/null | head -c 40 || echo module)"
SESSION="ao-${MOD_NAME}"

run_loop() {
  local n=0
  local args=(--offline)
  [[ $LIVE -eq 1 ]] && args=(--live)
  [[ $LOCAL -eq 1 ]] && args+=(--local)
  [[ -n "$MODULE" ]] && args+=(--module "$MODULE")
  [[ -n "$PROJECT_ROOT" ]] && args+=(--project-root "$PROJECT_ROOT")

  echo "[auto-optimizer] loop start module=${MODULE:-active} root=$PROJECT_ROOT" | tee -a "$HARNESS/loop.log"
  while true; do
    if [[ -f "$HARNESS/STOP" ]]; then
      echo "[auto-optimizer] STOP file present; exiting loop" | tee -a "$HARNESS/loop.log"
      rm -f "$HARNESS/STOP"
      break
    fi
    n=$((n + 1))
    if [[ -n "$MAX_CYCLES" && "$n" -gt "$MAX_CYCLES" ]]; then
      echo "[auto-optimizer] max-cycles $MAX_CYCLES reached" | tee -a "$HARNESS/loop.log"
      break
    fi
    echo "[auto-optimizer] cycle $n starting $(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "$HARNESS/loop.log"
    set +e
    uv run --with-requirements "$REQ" python "$SCRIPTS/run_cycle.py" "${args[@]}" >>"$HARNESS/loop.log" 2>&1
    rc=$?
    set -e
    echo "[auto-optimizer] cycle $n finished rc=$rc" | tee -a "$HARNESS/loop.log"
    if [[ $rc -ne 0 && $STOP_ON_FAIL -eq 1 ]]; then
      echo "[auto-optimizer] stop-on-fail" | tee -a "$HARNESS/loop.log"
      break
    fi
    if [[ "$INTERVAL" != "0" && -n "$INTERVAL" ]]; then
      # support Ns/Nm/Nh simple forms
      sleep_secs="$INTERVAL"
      if [[ "$INTERVAL" =~ ^([0-9]+)s$ ]]; then sleep_secs="${BASH_REMATCH[1]}"
      elif [[ "$INTERVAL" =~ ^([0-9]+)m$ ]]; then sleep_secs=$(( ${BASH_REMATCH[1]} * 60 ))
      elif [[ "$INTERVAL" =~ ^([0-9]+)h$ ]]; then sleep_secs=$(( ${BASH_REMATCH[1]} * 3600 ))
      fi
      sleep "$sleep_secs" || true
    fi
  done
}

if [[ $NO_TMUX -eq 1 ]]; then
  run_loop
  exit 0
fi

if ! command -v tmux >/dev/null 2>&1; then
  echo "warning: tmux not found; running in foreground (--no-tmux)" | tee -a "$HARNESS/loop.log"
  run_loop
  exit 0
fi

# Export function body by running script in tmux with env
export AO_LOOP_MODULE="$MODULE"
export AO_LOOP_MAX="$MAX_CYCLES"
export AO_LOOP_INTERVAL="$INTERVAL"
export AO_LOOP_LOCAL="$LOCAL"
export AO_LOOP_LIVE="$LIVE"
export AO_LOOP_STOP_ON_FAIL="$STOP_ON_FAIL"
export AO_LOOP_PROJECT_ROOT="$PROJECT_ROOT"
export AO_LOOP_SKILL_DIR="$SKILL_DIR"

if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "tmux session already exists: $SESSION"
  echo "attach: tmux attach -t $SESSION"
  exit 0
fi

tmux new-session -d -s "$SESSION" "bash '$BIN_DIR/start-loop.sh' --no-tmux ${MODULE:+--module $MODULE} ${MAX_CYCLES:+--max-cycles $MAX_CYCLES} ${INTERVAL:+--interval $INTERVAL} $([[ $LOCAL -eq 1 ]] && echo --local) $([[ $LIVE -eq 1 ]] && echo --live) $([[ $STOP_ON_FAIL -eq 1 ]] && echo --stop-on-fail)"
echo "started tmux session: $SESSION"
echo "  attach: tmux attach -t $SESSION"
echo "  stop:   auto-optimizer stop"
