#!/bin/zsh
# ============================================================
# Bridge Hand Generator — Launcher
#
# Double-click this file to start the Bridge Hand Generator.
# (Run setup.command first if this is your first time.)
# ============================================================

set -euo pipefail

# -- Resolve the directory this script lives in --
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# -- Use the venv's Python directly (no PATH dependency) --
PYTHON="$SCRIPT_DIR/.venv/bin/python"

if [[ ! -x "$PYTHON" ]]; then
    echo ""
    echo "ERROR: Virtual environment not found."
    echo "Please run setup.command first."
    echo ""
    echo "Press any key to close..."
    read -k 1
    exit 1
fi

# -- Launch the app --
echo ""
echo "=== Bridge Hand Generator ==="
echo ""
"$PYTHON" -m bridge_engine

echo ""
echo "=== Session ended ==="
echo ""
echo "Press any key to close..."
read -k 1
