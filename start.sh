#!/usr/bin/env bash
# Starts the bot on Linux/macOS: prepares the environment, installs libraries,
# starts the bot again when it asks for a restart (exit code 42).
# Usage:  bash start.sh

cd "$(dirname "$0")" || exit 1
PY=".venv/bin/python"

# A .venv left by a failed first start (e.g. without python3-venv) has no pip: it is made again
if [ -x "$PY" ] && ! "$PY" -m pip --version >/dev/null 2>&1; then
    echo "The Python environment in the .venv folder is incomplete: creating it again..."
    rm -rf .venv
fi

if [ ! -x "$PY" ]; then
    echo "[First start] Creating the Python environment..."
    SYSPY="$(command -v python3 || command -v python)"
    if [ -z "$SYSPY" ]; then
        echo "ERROR: Python was not found."
        echo "On Ubuntu/Debian install it with: sudo apt install -y python3 python3-venv python3-pip"
        exit 1
    fi
    if ! "$SYSPY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
        echo "ERROR: The bot needs Python 3.10 or newer. Install Python 3.12-3.14 and run start.sh again."
        exit 1
    fi
    if ! "$SYSPY" -m venv .venv || ! "$PY" -m pip --version >/dev/null 2>&1; then
        rm -rf .venv
        echo "ERROR: Could not create the Python environment."
        echo "On Ubuntu/Debian install: sudo apt install -y python3-venv python3-pip   and run start.sh again."
        exit 1
    fi
fi

if ! "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
    echo "ERROR: The bot needs Python 3.10 or newer. Install Python 3.12-3.14 and delete the .venv folder."
    exit 1
fi

if [ ! -f ".env" ]; then
    [ -f ".env.example" ] && cp ".env.example" ".env"
    chmod 600 .env 2>/dev/null
    echo "The .env file was not found - it was created from the template."
    echo "Paste your DISCORD_TOKEN into it (e.g. with: nano .env), save the file"
    echo "and run start.sh again."
    exit 1
fi
if ! grep -Eq '^DISCORD_TOKEN=.+' .env || grep -q '^DISCORD_TOKEN=your_bot_token_here' .env; then
    echo "ERROR: The .env file has no bot token yet (DISCORD_TOKEN)."
    echo "Open it (e.g. nano .env), paste the token after DISCORD_TOKEN= and run start.sh again."
    echo "The token is in Discord Developer Portal -> your app -> Bot -> Reset Token."
    exit 1
fi

export BOT_LAUNCHER="start.sh"

while true; do
    echo "Checking libraries..."
    if ! "$PY" -m pip install -r requirements.txt --disable-pip-version-check -q; then
        echo "ERROR: Could not install the libraries. Check your internet connection."
        echo "Still failing? Your Python may be newer than the bot was tested on (3.14): install 3.13 or 3.14,"
        echo "delete the .venv folder and run start.sh again."
        exit 1
    fi

    echo "Starting the bot..."
    "$PY" main.py
    code=$?

    if [ "$code" -eq 42 ]; then
        echo "Restarting the bot in a few seconds..."
        sleep 3
        continue
    fi
    if [ "$code" -eq 4 ]; then
        echo "This bot is already running (another start.sh or start.bat). Stop that one first."
        exit 4
    fi
    if [ "$code" -ne 0 ]; then
        echo "The bot stopped with an error (code $code). Details: data/logs/bot.log"
    fi
    exit "$code"
done
