#!/bin/bash
cd "$(dirname "$0")"

# Kill any existing run_telegram.py processes
EXISTING_PIDS=$(pgrep -f "run_telegram.py")
if [ -n "$EXISTING_PIDS" ]; then
    echo "[!] Existing trading bot detected. Killing..."
    echo "$EXISTING_PIDS" | xargs kill 2>/dev/null
    sleep 2
fi

echo "Starting Kkabi Trading Bot... (auto-restart on crash, Ctrl+C to stop)"
echo ""

while true; do
    python3 run_telegram.py
    EXIT_CODE=$?
    echo ""
    echo "[!] Kkabi Trading Bot exited (code: $EXIT_CODE). Restarting in 3 seconds..."
    echo "    Press Ctrl+C to stop."
    sleep 3
done
