#!/usr/bin/env bash
# Opens a new Ghostty tab with runserver (left) and the Celery worker (right) side by side.
# Usage: ./dev.sh [port]   (default 8001). Requires Ghostty 1.3+ (AppleScript) and a running Redis.
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
PORT="${1:-8001}"

osascript - "$DIR" "$PORT" >/dev/null <<'APPLESCRIPT'
on run argv
    set projectDir to item 1 of argv
    set serverPort to item 2 of argv
    set venv to "pyenv activate hy_env && "
    tell application "Ghostty"
        activate
        set cfg to new surface configuration
        set initial working directory of cfg to projectDir
        set initial input of cfg to venv & "python manage.py runserver 0:" & serverPort & linefeed
        if (count of windows) is 0 then
            set win to new window with configuration cfg
            set t to selected tab of win
        else
            set t to new tab in front window with configuration cfg
        end if
        set name override of t to "dev"
        set leftPane to focused terminal of t

        set cfg2 to new surface configuration from cfg
        set initial input of cfg2 to venv & "celery -A config worker -l info -P threads" & linefeed
        split leftPane direction right with configuration cfg2
    end tell
end run
APPLESCRIPT
