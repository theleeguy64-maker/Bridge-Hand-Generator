"""
backup_profiles.py

Utility script to back up all JSON profile files before making schema changes.

- Looks for *.json files in a "profiles" directory under the current working
  directory (typically the Exec/project root).
- For each JSON file, creates a copy with suffix ".backup" (or
  ".backup.N" if that already exists).

Usage (from Exec root):
    python backup_profiles.py

This script is intentionally conservative and never overwrites the originals.
"""

from __future__ import annotations

import shutil
from pathlib import Path


def backup_profiles(profiles_dir: Path) -> None:
    if not profiles_dir.exists():
        raise SystemExit(f"Profiles directory not found: {profiles_dir}")

    json_files = sorted(profiles_dir.glob("*.json"))
    if not json_files:
        print(f"No JSON files found in {profiles_dir}")
        return

    print(f"Backing up {len(json_files)} profile file(s) from {profiles_dir}")
    for jf in json_files:
        backup_path = jf.with_suffix(jf.suffix + ".backup")
        # If .backup exists, add numeric suffix
        counter = 1
        while backup_path.exists():
            backup_path = jf.with_suffix(jf.suffix + f".backup{counter}")
            counter += 1

        shutil.copy2(jf, backup_path)
        print(f"  {jf.name} -> {backup_path.name}")


def main() -> None:
    root = Path(__file__).resolve().parent
    profiles_dir = root / "profiles"
    backup_profiles(profiles_dir)


if __name__ == "__main__":
    main()
