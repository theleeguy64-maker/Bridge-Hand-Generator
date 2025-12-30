"""
Package entry point.

Allows:
  python -m bridge_engine ...

Delegates to the orchestrator CLI.
"""

from __future__ import annotations
from .orchestrator import main

if __name__ == "__main__":
    main()
    