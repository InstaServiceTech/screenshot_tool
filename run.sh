#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
python3 -m venv .venv 2>/dev/null || true
source .venv/bin/activate
pip install -q -r requirements.txt
# Local-only default. Never applied on the hosted container.
if [ ! -f .env ]; then
  printf '%s\n' 'SECRET_KEY=local-dev-only' 'AUTH_USERS=user:user' > .env
fi
cd app
echo "Open http://127.0.0.1:5000"
python app.py
