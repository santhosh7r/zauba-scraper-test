#!/usr/bin/env bash
#
# run_forever.sh — keep the scraper running without systemd / root.
#
# Relaunches bot.py whenever it exits for any reason. Use this if you can't
# install the systemd service.
#
#   chmod +x run_forever.sh
#   ./run_forever.sh                 # run in the foreground
#   nohup ./run_forever.sh &         # run detached, survives logout
#
# To also survive a VPS reboot, add this to your crontab (crontab -e):
#   @reboot /home/santhosh/dev/zauba_scraper/run_forever.sh >> /home/santhosh/dev/zauba_scraper/logs/service.log 2>&1
#
set -u

cd "$(dirname "$0")" || exit 1

PYTHON="./venv/bin/python3"
[ -x "$PYTHON" ] || PYTHON="python3"

RESTART_DELAY=30

while true; do
    echo "[run_forever] $(date '+%Y-%m-%d %H:%M:%S') starting bot.py"
    "$PYTHON" bot.py
    code=$?
    if [ "$code" -eq 130 ]; then
        echo "[run_forever] interrupted by user (Ctrl-C) — stopping."
        exit 0
    fi
    echo "[run_forever] $(date '+%Y-%m-%d %H:%M:%S') bot.py exited (code $code) — restarting in ${RESTART_DELAY}s"
    sleep "$RESTART_DELAY"
done
