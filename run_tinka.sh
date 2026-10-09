#!/usr/bin/env bash
set -e

WORKSPACE="/home/bambiblack808/workspace/ai-unified-backups"
VENV="${WORKSPACE}/.venv"
PID_DIR="${WORKSPACE}/.pids"
LOG_DIR="${WORKSPACE}/logs"

mkdir -p "${PID_DIR}" "${LOG_DIR}"

# 1. Activate Python virtual environment
if [ -f "${VENV}/bin/activate" ]; then
    source "${VENV}/bin/activate"
fi

cd "${WORKSPACE}"

# 2. Check and launch Dashboard (port 8080)
if [ -f "${PID_DIR}/dashboard.pid" ] && kill -0 "$(cat "${PID_DIR}/dashboard.pid")" 2>/dev/null; then
    echo "[*] Dashboard already running (PID: $(cat "${PID_DIR}/dashboard.pid"))."
else
    echo "[*] Starting Tinka Mission Control Dashboard..."
    fuser -k 8080/tcp 2>/dev/null || true
    nohup python3 -u tinka_dashboard.py 8080 > "${LOG_DIR}/dashboard.log" 2>&1 &
    echo $! > "${PID_DIR}/dashboard.pid"
    echo "[✓] Dashboard launched (PID: $!)."
fi

# 3. Check and launch Autonomous Daemon
if [ -f "${PID_DIR}/daemon.pid" ] && kill -0 "$(cat "${PID_DIR}/daemon.pid")" 2>/dev/null; then
    echo "[*] Autonomous Daemon already running (PID: $(cat "${PID_DIR}/daemon.pid"))."
else
    echo "[*] Starting Tinka Autonomous Engine Daemon..."
    nohup python3 -u tinka_daemon.py > "${LOG_DIR}/daemon.log" 2>&1 &
    echo $! > "${PID_DIR}/daemon.pid"
    echo "[✓] Daemon launched (PID: $!)."
fi

# 4. Check and launch Webhook Ingestion Listener (port 8081)
if [ -f "${PID_DIR}/webhook.pid" ] && kill -0 "$(cat "${PID_DIR}/webhook.pid")" 2>/dev/null; then
    echo "[*] Webhook Listener already running (PID: $(cat "${PID_DIR}/webhook.pid"))."
else
    echo "[*] Starting Tinka Webhook Inflow Listener..."
    fuser -k 8081/tcp 2>/dev/null || true
    nohup python3 -u tinka_webhook_listener.py 8081 > "${LOG_DIR}/webhook.log" 2>&1 &
    echo $! > "${PID_DIR}/webhook.pid"
    echo "[✓] Webhook Listener launched (PID: $!)."
fi
