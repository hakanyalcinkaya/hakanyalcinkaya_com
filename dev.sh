#!/usr/bin/env bash
# Splits the current Ghostty pane: runserver stays here (left), the Celery worker opens on the right.
# Usage: ./dev.sh [port]   (default: first free port in 8000-8003). Requires Ghostty 1.3+ (AppleScript) and a running Redis.
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
PORT="${1:-}"
if [[ -z "$PORT" ]]; then
    # First free port from 8000 to 8003.
    for candidate in 8000 8001 8002 8003; do
        if ! lsof -nP -iTCP:"$candidate" -sTCP:LISTEN >/dev/null 2>&1; then
            PORT="$candidate"
            break
        fi
    done
    if [[ -z "$PORT" ]]; then
        echo "Ports 8000-8003 are all in use." >&2
        exit 1
    fi
fi

osascript - "$DIR" "$(tty)" >/dev/null <<'APPLESCRIPT'
on run argv
    set projectDir to item 1 of argv
    set myTty to item 2 of argv
    tell application "Ghostty"
        set here to missing value
        repeat with term in terminals
            if tty of term is myTty then set here to term
        end repeat
        if here is missing value then set here to focused terminal of selected tab of front window

        set cfg to new surface configuration
        set initial working directory of cfg to projectDir
        set initial input of cfg to "pyenv activate hy_env && celery -A config worker -l info -P threads" & linefeed
        split here direction right with configuration cfg
        focus here
    end tell
end run
APPLESCRIPT

cd "$DIR"
PYENV_VERSION=hy_env exec pyenv exec python manage.py runserver "0:$PORT"
