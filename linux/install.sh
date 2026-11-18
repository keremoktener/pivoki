#!/usr/bin/env bash
set -euo pipefail

source_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
prefix="${HOME}/.local"
use_drop=yes
while (($#)); do
    case "$1" in
        --prefix) prefix="${2:?Supply an absolute install prefix}"; shift 2 ;;
        --no-drop) use_drop=no; shift ;;
        --help|-h) echo 'Usage: linux/install.sh [--prefix /absolute/user/prefix] [--no-drop]'; exit 0 ;;
        *) echo "Unknown option: $1" >&2; exit 64 ;;
    esac
done
if [[ "$prefix" != /* ]]; then
    echo "Use an absolute install prefix." >&2
    exit 64
fi
python_bin="${PYTHON:-python3}"
"$python_bin" - <<'PY'
import sys
if sys.version_info < (3, 11):
    raise SystemExit("Pivoki requires Python 3.11 or later.")
try:
    import tkinter
except ImportError:
    raise SystemExit("Install your distribution’s Tk bindings for this Python (python3-tk on Ubuntu).")
PY
venv="$prefix/share/pivoki/desktop-venv"
"$python_bin" -m venv "$venv"
desktop="$source_dir"
if [[ "$use_drop" == yes ]]; then desktop="$source_dir[drop]"; fi
"$venv/bin/python" -m pip install "$source_dir/../engine" "$source_dir/../studio" "$desktop"
mkdir -p "$prefix/bin" "$prefix/share/applications"
"$venv/bin/python" - "$prefix" "$source_dir" <<'PY'
from pathlib import Path
import shlex
import sys

prefix, source = map(Path,sys.argv[1:])
executable = prefix / "share/pivoki/desktop-venv/bin/pivoki-desktop"
launcher = prefix / "bin/pivoki-desktop"
launcher.write_text("#!/bin/sh\nexec " + shlex.quote(str(executable)) + ' "$@"\n')
launcher.chmod(0o755)
# Desktop Entry Exec quoting is distinct from shell quoting. Use the installed
# absolute binary so graphical sessions need no custom PATH.
escaped = str(launcher).replace("\\","\\\\\\\\").replace('"', '\\\\"').replace("`","\\\\`").replace("$","\\\\$").replace("%","%%")
template = (source / "org.pivoki.Desktop.desktop").read_text()
template = template.replace("Exec=pivoki-desktop %F", 'Exec="' + escaped + '" %F')
template = template.replace("TryExec=pivoki-desktop\n","")
(prefix / "share/applications/org.pivoki.Desktop.desktop").write_text(template)
print("Installed " + str(launcher))
PY
