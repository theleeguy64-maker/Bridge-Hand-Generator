#!/bin/zsh
# ============================================================
# Bridge Hand Generator — One-Time Setup
#
# What this does:
#   1. Checks for Python 3.11+ (installs via Homebrew if needed)
#   2. Creates a virtual environment (.venv)
#   3. Runs a smoke test to confirm everything works
#
# Run this once after unzipping. After that, use run.command.
# ============================================================

set -euo pipefail

# -- Resolve the directory this script lives in --
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo "=== Bridge Hand Generator — Setup ==="
echo ""
echo "Working directory: $SCRIPT_DIR"
echo ""

# -- Step 1: Check for Python 3.11+ --
PYTHON_CMD=""

# Check common Python locations
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        version=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "0.0")
        major=$(echo "$version" | cut -d. -f1)
        minor=$(echo "$version" | cut -d. -f2)
        if [[ "$major" -ge 3 && "$minor" -ge 11 ]]; then
            PYTHON_CMD="$cmd"
            echo "Found Python $version at $(command -v "$cmd")"
            break
        fi
    fi
done

if [[ -z "$PYTHON_CMD" ]]; then
    echo "Python 3.11+ not found."
    echo ""

    # Check for Homebrew
    if ! command -v brew &>/dev/null; then
        echo "Homebrew not found. Installing Homebrew first..."
        echo "(This is the standard macOS package manager)"
        echo ""
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

        # Add Homebrew to PATH for this session (Apple Silicon vs Intel)
        if [[ -f /opt/homebrew/bin/brew ]]; then
            eval "$(/opt/homebrew/bin/brew shellenv)"
        elif [[ -f /usr/local/bin/brew ]]; then
            eval "$(/usr/local/bin/brew shellenv)"
        fi
        echo ""
    fi

    echo "Installing Python 3.13 via Homebrew..."
    brew install python@3.13
    PYTHON_CMD="python3"

    # Verify it worked
    version=$("$PYTHON_CMD" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "0.0")
    echo "Installed Python $version"
fi

echo ""

# -- Step 2: Create virtual environment --
if [[ -d ".venv" ]]; then
    echo "Virtual environment (.venv) already exists — skipping creation."
else
    echo "Creating virtual environment..."
    "$PYTHON_CMD" -m venv .venv
    echo "Virtual environment created at .venv/"
fi

# Activate it
source .venv/bin/activate
echo ""

# -- Step 3: Smoke test --
echo "Running smoke test..."
python -c "from bridge_engine.orchestrator import main; print('Import OK')"

if [[ $? -eq 0 ]]; then
    echo ""
    echo "=== Setup complete! ==="
    echo ""
    echo "To run the Bridge Hand Generator:"
    echo "  Double-click run.command"
    echo "  — or —"
    echo "  Open Terminal and run: $SCRIPT_DIR/run.command"
    echo ""
else
    echo ""
    echo "=== Setup FAILED ==="
    echo "The smoke test did not pass. Please check the error above."
    echo ""
fi

# Keep window open so user can read the output
echo "Press any key to close..."
read -k 1
