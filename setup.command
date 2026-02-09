#!/bin/zsh
# ============================================================
# Bridge Hand Generator — One-Time Setup
#
# What this does:
#   1. Checks for Python 3.11+ (guides you to install it if needed)
#   2. Creates a virtual environment (.venv)
#   3. Runs a smoke test to confirm everything works
#
# All output is logged to setup_log.txt. If something goes wrong,
# send that file to the developer.
#
# Run this once after unzipping. After that, use run.command.
# ============================================================

# -- Resolve the directory this script lives in --
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# -- Start logging (screen + file) --
LOG_FILE="$SCRIPT_DIR/setup_log.txt"
exec > >(tee "$LOG_FILE") 2>&1

echo ""
echo "=== Bridge Hand Generator — Setup ==="
echo ""
echo "Date    : $(date)"
echo "macOS   : $(sw_vers -productVersion 2>/dev/null || echo 'unknown')"
echo "Chip    : $(uname -m)"
echo "Dir     : $SCRIPT_DIR"
echo ""

# -- Step 1: Check for Python 3.11+ --
find_python() {
    # Check common Python locations (including python.org default install path)
    for cmd in python3 \
               /usr/local/bin/python3 \
               /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 \
               /Library/Frameworks/Python.framework/Versions/3.12/bin/python3 \
               /Library/Frameworks/Python.framework/Versions/3.11/bin/python3 \
               python; do
        if command -v "$cmd" &>/dev/null || [[ -x "$cmd" ]]; then
            version=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "0.0")
            major=$(echo "$version" | cut -d. -f1)
            minor=$(echo "$version" | cut -d. -f2)
            if [[ "$major" -ge 3 && "$minor" -ge 11 ]]; then
                PYTHON_CMD="$cmd"
                echo "Found Python $version at $(command -v "$cmd" 2>/dev/null || echo "$cmd")"
                return 0
            fi
        fi
    done
    return 1
}

PYTHON_CMD=""

if find_python; then
    : # found, PYTHON_CMD is set
else
    echo "Python 3.11+ not found on this Mac."
    echo ""
    echo "============================================"
    echo "  Please install Python from python.org"
    echo "============================================"
    echo ""
    echo "A download page will open in your browser."
    echo "Install Python using the standard macOS installer"
    echo "(click through the steps like any Mac app install)."
    echo ""

    # Open the python.org downloads page in the default browser
    open "https://www.python.org/downloads/"

    echo "After the install finishes, come back here and press Enter."
    echo ""

    # Wait for user, then retry
    while true; do
        echo -n "Press Enter to continue (or type 'q' to quit): "
        read response
        if [[ "$response" == "q" || "$response" == "Q" ]]; then
            echo "Setup cancelled by user."
            echo ""
            echo "Press any key to close..."
            read -k 1
            exit 1
        fi

        echo ""
        echo "Checking for Python again..."
        if find_python; then
            break
        else
            echo ""
            echo "Still not found. Make sure the Python installer completed."
            echo "(If you just installed it, try pressing Enter again.)"
            echo ""
        fi
    done
fi

echo ""

# -- Step 2: Create virtual environment --
if [[ -d ".venv" ]]; then
    echo "Virtual environment (.venv) already exists — skipping creation."
else
    echo "Creating virtual environment..."
    if "$PYTHON_CMD" -m venv .venv; then
        echo "Virtual environment created."
    else
        echo ""
        echo "=== Setup FAILED ==="
        echo "Could not create virtual environment."
        echo ""
        echo "Please send this file to the developer:"
        echo "  $LOG_FILE"
        echo ""
        echo "Press any key to close..."
        read -k 1
        exit 1
    fi
fi

echo ""

# -- Step 3: Smoke test --
echo "Running smoke test..."
VENV_PYTHON="$SCRIPT_DIR/.venv/bin/python"

if "$VENV_PYTHON" -c "from bridge_engine.orchestrator import main; print('Import OK')"; then
    echo ""
    echo "=== Setup complete! ==="
    echo ""
    echo "To run the Bridge Hand Generator:"
    echo "  Double-click run.command"
    echo ""
else
    echo ""
    echo "=== Setup FAILED ==="
    echo "The smoke test did not pass."
    echo ""
    echo "Please send this file to the developer:"
    echo "  $LOG_FILE"
    echo ""
fi

# Keep window open so user can read the output
echo "Press any key to close..."
read -k 1
