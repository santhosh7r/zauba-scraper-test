#!/usr/bin/env bash
#
# install.sh — one-command setup for the Zauba scraper.
#
# On your VPS, just run:
#     bash install.sh
#
# It creates the virtualenv, installs everything, installs the browser,
# prepares your .env, and generates a systemd service for THIS machine.
#
set -e

cd "$(dirname "$0")"
PROJECT_DIR="$(pwd)"
RUN_USER="$(whoami)"

echo "=================================================="
echo "  Zauba Scraper — installer"
echo "  Project : $PROJECT_DIR"
echo "  User    : $RUN_USER"
echo "=================================================="

# --- 1. Python check -------------------------------------------------------
if ! command -v python3 >/dev/null 2>&1; then
    echo "ERROR: python3 is not installed. Install it first:"
    echo "   Debian/Ubuntu : sudo apt install -y python3 python3-venv python3-pip"
    echo "   Fedora/RHEL   : sudo dnf install -y python3 python3-pip"
    exit 1
fi
echo "==> Using $(python3 --version)"

# --- 2. Virtual environment ------------------------------------------------
if [ ! -d venv ]; then
    echo "==> Creating virtual environment (venv/)..."
    if ! python3 -m venv venv 2>/dev/null; then
        echo "ERROR: could not create a virtualenv. Install the venv package:"
        echo "   Debian/Ubuntu : sudo apt install -y python3-venv python3-full"
        echo "   Fedora/RHEL   : sudo dnf install -y python3"
        echo "...then re-run:  bash install.sh"
        exit 1
    fi
else
    echo "==> Reusing existing venv/"
fi

# --- 3. Python packages ----------------------------------------------------
echo "==> Installing Python packages..."
./venv/bin/pip install --quiet --upgrade pip
./venv/bin/pip install -r requirements.txt
echo "    Packages installed."

# --- 4. Playwright browser (Cloudflare fallback) ---------------------------
echo "==> Installing Playwright Chromium browser..."
if ./venv/bin/playwright install --with-deps chromium; then
    echo "    Chromium + system libraries installed."
else
    echo "    Could not install system libraries (needs root) — trying browser only..."
    ./venv/bin/playwright install chromium \
        || echo "    WARNING: browser install failed. The bot still works in httpx-only mode."
fi

# --- 4b. Xvfb virtual display (for the headless=False browser) -------------
echo "==> Installing Xvfb (virtual display for the human-mode browser)..."
if command -v Xvfb >/dev/null 2>&1; then
    echo "    Xvfb already installed."
elif command -v apt-get >/dev/null 2>&1; then
    sudo apt-get install -y xvfb \
        || echo "    WARNING: could not install xvfb (need sudo) — browser will run headless."
elif command -v dnf >/dev/null 2>&1; then
    sudo dnf install -y xorg-x11-server-Xvfb \
        || echo "    WARNING: could not install xvfb — browser will run headless."
else
    echo "    WARNING: unknown package manager — install Xvfb manually for headful mode."
fi

# --- 5. .env ---------------------------------------------------------------
if [ ! -f .env ]; then
    cp .env.example .env
    echo "==> Created .env — you MUST edit it with your Supabase details."
else
    echo "==> .env already exists — leaving it as is."
fi

# --- 6. systemd service generated for this machine -------------------------
SERVICE_FILE="zauba-scraper.service"
cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Zauba Corp Continuous Scraper
After=network-online.target
Wants=network-online.target
StartLimitIntervalSec=0

[Service]
Type=simple
User=$RUN_USER
WorkingDirectory=$PROJECT_DIR

# The browser runs headless=False to look human. On a screenless VPS the bot
# starts its own Xvfb virtual display automatically (pyvirtualdisplay); the
# Xvfb package is installed by this script.
ExecStart=$PROJECT_DIR/venv/bin/python3 $PROJECT_DIR/bot.py

Restart=always
RestartSec=30
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
chmod +x run_forever.sh 2>/dev/null || true
echo "==> Generated $SERVICE_FILE with this machine's paths."

# --- Done ------------------------------------------------------------------
cat <<EOF

==================================================
  SETUP COMPLETE
==================================================

STEP 1 — add your Supabase keys:
    nano .env

STEP 2 — start the scraper (pick ONE):

  A) systemd  (recommended — auto-restarts + starts on reboot)
       sudo cp zauba-scraper.service /etc/systemd/system/
       sudo systemctl daemon-reload
       sudo systemctl enable --now zauba-scraper
       journalctl -u zauba-scraper -f      # watch live

  B) no root needed
       nohup ./run_forever.sh &            # runs in background
       tail -f logs/scraper.log            # watch live

To test first (one sweep then exit):
    ./venv/bin/python3 bot.py --once
==================================================
EOF
