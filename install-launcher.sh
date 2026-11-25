#!/usr/bin/env bash
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
apps="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
icons="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/scalable/apps"
bin="$HOME/.local/bin"
mkdir -p "$apps" "$icons" "$bin"
printf '#!/usr/bin/env bash\nexec bash %q "$@"\n' "$root/run.sh" > "$bin/sakura-dashboard"
chmod 755 "$bin/sakura-dashboard"
cat > "$icons/sakura.svg" <<'EOF'
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128"><rect width="128" height="128" rx="28" fill="#201329"/><g fill="#f478d7" transform="translate(64 64)"><path id="p" d="M0 0C-34-12-31-49-9-43L0-34 9-43C31-49 34-12 0 0Z"/><use href="#p" transform="rotate(72)"/><use href="#p" transform="rotate(144)"/><use href="#p" transform="rotate(216)"/><use href="#p" transform="rotate(288)"/></g><circle cx="64" cy="64" r="8" fill="#fff0fa"/></svg>
EOF
cat > "$apps/sakura.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Sakura
Comment=Unified music, game sync, RGB and system dashboard
Exec="$bin/sakura-dashboard"
Icon=sakura
Terminal=false
Categories=Utility;AudioVideo;
StartupNotify=true
EOF
# Hide previous Sakura-specific menu entries without removing their applications.
for file in "$apps"/*.desktop; do
  [[ -f "$file" && "$file" != "$apps/sakura.desktop" ]] || continue
  if grep -Eiq '^Name=(Sakura([[:space:]•-]+)(Game[ -]Sync|Dashboard|Connect|Night))([[:space:]]*)$' "$file"; then
    if grep -q '^NoDisplay=' "$file"; then
      sed -i 's/^NoDisplay=.*/NoDisplay=true/' "$file"
    else
      sed -i '/^\[Desktop Entry\]$/a NoDisplay=true' "$file"
    fi
    printf 'Hidden old launcher: %s\n' "$file"
  fi
done
if command -v kbuildsycoca6 >/dev/null; then kbuildsycoca6 >/dev/null 2>&1 || true; fi
printf 'Installed Sakura launcher. Search for Sakura in your KDE application menu.\n'
