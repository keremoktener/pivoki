#!/usr/bin/env bash
# Use a private venv and compile for the current Mac's architecture.
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ "$(uname -s)" != Darwin ]]; then
  echo "Build the macOS bundle on a Mac." >&2
  exit 1
fi
python_bin="${PIVOKI_PYTHON:-}"
if [[ -z "$python_bin" ]]; then
  for candidate in python3.12 python3.11 python3.13 python3; do
    if command -v "$candidate" >/dev/null && "$candidate" -c 'import sys, tkinter; assert sys.version_info >= (3,11)' 2>/dev/null; then
      python_bin="$candidate"
      break
    fi
  done
fi
if [[ -z "$python_bin" ]]; then
  echo "Set PIVOKI_PYTHON to a Python 3.11+ interpreter with Tk." >&2
  exit 1
fi
venv="$PWD/.build/pivoki-python"
"$python_bin" -m venv "$venv"
"$venv/bin/python" -m pip install --disable-pip-version-check --constraint scripts/build-constraints.txt './engine[heif]' './studio[raw]' pyinstaller
"$venv/bin/python" scripts/build_engine.py --raw
exec macos/build-app.sh release
