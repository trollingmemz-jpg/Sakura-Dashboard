#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
root="$PWD"
sync="$HOME/.local/share/sakura-game-sync"
state="$HOME/.config/sakura-game-sync"
logs="${XDG_STATE_HOME:-$HOME/.local/state}/sakura"
mkdir -p "$logs"
log="$logs/update.log"
# Avoid overlapping startup updates; never block normal launch on another updater.
exec 9>"$logs/update.lock"
if flock -n 9; then
 (
  export GIT_TERMINAL_PROMPT=0 GCM_INTERACTIVE=Never
  export GIT_SSH_COMMAND="ssh -o BatchMode=yes -o ConnectTimeout=5"
  update_repo() {
   local path="$1" before after remote dirty
   if ! git -C "$path" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "Skipped: not a repository: $path"; return 1
   fi
   if [[ "$(git -C "$path" branch --show-current)" != main ]]; then
    echo "Skipped: not on main: $path"; return 1
   fi
   dirty="$(git -C "$path" status --porcelain --untracked-files=no)" || return 1
   if [[ -n "$dirty" ]]; then echo "Skipped: local tracked changes: $path"; return 1; fi
   before="$(git -C "$path" rev-parse HEAD)" || return 1
   timeout 12s git -C "$path" fetch --no-tags origin main || { echo "Fetch failed: $path"; return 1; }
   remote="$(git -C "$path" rev-parse FETCH_HEAD)" || return 1
   if [[ "$before" == "$remote" ]]; then echo "Up to date: $path"; return 1; fi
   git -C "$path" merge-base --is-ancestor "$before" "$remote" || { echo "Skipped: non-fast-forward history: $path"; return 1; }
   git -C "$path" branch -f sakura-backup "$before" || return 1
   git -C "$path" merge --ff-only "$remote" || return 1
   after="$(git -C "$path" rev-parse HEAD)" || return 1
   echo "Updated: $path $before -> $after"
   [[ "$before" != "$after" ]]
  }
  echo "=== $(date -Is) ==="
  update_repo "$root" || true
  if update_repo "$sync"; then
   mkdir -p "$state"
   if [[ -f "$state/dashboard-status.json" ]]; then
    touch "$state/dashboard-restart.request"
   fi
  fi
 ) >>"$log" 2>&1 || true
 flock -u 9
fi
exec 9>&-
if [[ ! -x .venv/bin/python ]]; then
    echo "Dashboard requires .venv with PySide6 and psutil." >&2
    exit 1
fi
# Refresh the installed optional lighting app without enabling it for new users.
if [[ -f "$HOME/.local/share/sakura-lighting/lighting.py" && -f optional/lighting.py ]]; then
    lighting_python="$sync/venv/bin/python"
    [[ -x "$lighting_python" ]] || lighting_python="$root/.venv/bin/python"
    if ! cmp -s optional/lighting.py "$HOME/.local/share/sakura-lighting/lighting.py"; then
        "$lighting_python" optional/lighting.py --install >>"$log" 2>&1 || true
    fi
fi
# QR generation fallback when the system qrencode utility is absent.
if ! command -v qrencode >/dev/null && ! .venv/bin/python -c 'import qrcode, PIL' >/dev/null 2>&1; then
    timeout 30s .venv/bin/python -m pip install 'qrcode[pil]>=7.4,<9' >>"$log" 2>&1 || true
fi
exec .venv/bin/python dashboard.py
