"""
Package entry point.

Allows:
  python -m bridge_engine ...

Delegates to the orchestration CLI.
"""
from __future__ import annotations

from .orchestration import main


if __name__ == "__main__":
    main()
