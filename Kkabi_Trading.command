#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PIDFILE="${SCRIPT_DIR}/.bot.pid"

# Kill any existing bot processes from THIS repo only
PIDS_TO_KILL=""

# 1. PID file: catches bots started from this repo (including relative-path manual launches)
if [ -f "$PIDFILE" ]; then
    OLD_PID=$(cat "$PIDFILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        PIDS_TO_KILL="$OLD_PID"
    fi
fi

# 2. Absolute-path pgrep: catches processes started via this launcher
ABS_PIDS=$(pgrep -f "${SCRIPT_DIR}/run_telegram.py" 2>/dev/null)
if [ -n "$ABS_PIDS" ]; then
    PIDS_TO_KILL=$(printf '%s\n%s' "$PIDS_TO_KILL" "$ABS_PIDS" | sort -un | sed '/^$/d')
fi

if [ -n "$PIDS_TO_KILL" ]; then
    echo "[!] Existing trading bot detected. Killing..."
    echo "$PIDS_TO_KILL" | xargs kill 2>/dev/null
    sleep 2
fi
rm -f "$PIDFILE"

echo "Starting Kkabi Trading Bot... (auto-restart on crash, Ctrl+C to stop)"
echo ""

BOT_PID=""
cleanup() {
    rm -f "$PIDFILE"
    [ -n "$BOT_PID" ] && kill "$BOT_PID" 2>/dev/null
    exit 0
}
trap cleanup INT TERM

while true; do
    python3 "${SCRIPT_DIR}/run_telegram.py" &
    BOT_PID=$!
    echo "$BOT_PID" > "$PIDFILE"
    wait "$BOT_PID"
    EXIT_CODE=$?
    BOT_PID=""
    rm -f "$PIDFILE"
    echo ""
    echo "[!] Kkabi Trading Bot exited (code: $EXIT_CODE). Restarting in 3 seconds..."
    echo "    Press Ctrl+C to stop."
    sleep 3
done
