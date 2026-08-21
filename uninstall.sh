#!/usr/bin/env bash
set -euo pipefail

plugin_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
purge=()

if [[ ${1:-} == "--purge" ]]; then
  purge=(--purge)
elif [[ $# -gt 0 ]]; then
  echo "Usage: $0 [--purge]" >&2
  exit 2
fi

python3 "$plugin_dir/scripts/keymap.py" uninstall "${purge[@]}"
omarchy-shell -q omarchy.menu refresh >/dev/null 2>&1 || true

echo "Shell integration removed. You can now run: omarchy plugin remove io.github.sahzudin.keymap"
