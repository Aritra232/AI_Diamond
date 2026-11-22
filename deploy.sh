#!/usr/bin/env bash
# One-shot setup / update script for the VPS (Ubuntu/Debian).
# Run from the project root:  bash deploy.sh
set -euo pipefail

cd "$(dirname "$0")"

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo ">> Installing ffmpeg (needed for audio mixing)"
  sudo apt-get update && sudo apt-get install -y ffmpeg
fi

if [ ! -d venv ]; then
  echo ">> Creating virtualenv"
  python3 -m venv venv
fi

echo ">> Installing Python dependencies"
venv/bin/pip install --upgrade pip
venv/bin/pip install -r requirements.txt

if [ ! -f .env ]; then
  echo "!! .env not found. Copy .env.example to .env and fill in the keys, then re-run."
  exit 1
fi

mkdir -p logs

if pm2 describe ai-diamond >/dev/null 2>&1; then
  echo ">> Reloading ai-diamond"
  pm2 reload ecosystem.config.js --update-env
else
  echo ">> Starting ai-diamond"
  pm2 start ecosystem.config.js
fi

pm2 save
pm2 status ai-diamond
