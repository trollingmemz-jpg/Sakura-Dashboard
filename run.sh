#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
if [[ ! -x .venv/bin/python ]]; then
    echo "Dashboard requires .venv with PySide6 and psutil." >&2
    exit 1
fi
exec .venv/bin/python dashboard.py
