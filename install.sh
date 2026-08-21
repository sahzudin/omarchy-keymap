#!/usr/bin/env bash
set -euo pipefail

plugin_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
with_bar=()

if [[ ${1:-} == "--with-bar" ]]; then
  with_bar=(--with-bar)
elif [[ $# -gt 0 ]]; then
  echo "Usage: $0 [--with-bar]" >&2
  exit 2
fi

omarchy-shell -q shell rescanPlugins >/dev/null 2>&1 || true
python3 "$plugin_dir/scripts/keymap.py" install "${with_bar[@]}"
omarchy-shell -q shell rescanPlugins >/dev/null 2>&1 || true
omarchy-shell -q omarchy.menu refresh >/dev/null 2>&1 || true

echo "Installed Keyboard Shortcuts. Open Setup > Keyboard > Keyboard Shortcuts."
