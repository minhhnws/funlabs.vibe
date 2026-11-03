#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PORT="${AUDIOFORGE_PORT:-8765}"
PYTHON="${PYTHON:-python3}"

cleanup() {
  if [[ -n "${API_PID:-}" ]]; then
    kill -INT "$API_PID" 2>/dev/null || true
    wait "$API_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

"$PYTHON" "$ROOT/audioforge/scripts/audioforge.py" --port "$PORT" --diagnostic &
API_PID=$!
READY=0
for _ in {1..30}; do
  if curl -fsS "http://127.0.0.1:$PORT/api/state" >/dev/null 2>&1; then READY=1; break; fi
  sleep 0.1
done
if [[ "$READY" != 1 ]]; then
  echo "AudioForge API did not become ready" >&2
  kill -INT "$API_PID" 2>/dev/null || true
  wait "$API_PID" 2>/dev/null || true
  exit 1
fi
if command -v xdg-open >/dev/null 2>&1 && [[ "${AUDIOFORGE_NO_BROWSER:-0}" != 1 ]]; then
  xdg-open "http://127.0.0.1:$PORT/" >/dev/null 2>&1 || true
fi
wait "$API_PID"
