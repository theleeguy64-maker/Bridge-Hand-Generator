"""
run_all.py
A simple script for macOS/desktop use:
1. Runs pytest on the project.
2. If tests pass, runs the orchestrator.
"""

import sys
import subprocess
from pathlib import Path

def main():
    project_root = Path(__file__).resolve().parent

    print("=== Running pytest ===")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(project_root / "tests")],
        cwd=project_root
    )

    if result.returncode != 0:
        print("Pytest failed — orchestrator will NOT run.")
        sys.exit(result.returncode)

    print("\n=== Tests passed. Running orchestrator ===")
    try:
        from bridge_engine import orchestrator
        orchestrator.main()
    except Exception as e:
        print(f"Error running orchestrator: {e}")
        raise

if __name__ == "__main__":
    main()
