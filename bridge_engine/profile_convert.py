from __future__ import annotations

import json
from pathlib import Path
from .hand_profile import validate_profile


def convert_profiles(dir_path: Path, write: bool = False) -> None:
    """
    Normalize all JSON profile files in a directory and stamp as schema v1.

    Validates each profile and writes it back with schema_version=1.
    This ensures any legacy defaults are applied and the profile is in
    the canonical format.

    Args:
        dir_path: Directory containing .json profile files
        write: If True, write changes to disk. If False, dry-run mode.
    """
    for path in dir_path.glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        profile = validate_profile(data)
        if write:
            # Get the dict representation and add schema_version
            # (to_dict() doesn't include schema_version, so we add it manually)
            output = profile.to_dict()
            output["schema_version"] = 1
            path.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
        else:
            print(f"Would convert: {path}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", required=True)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    convert_profiles(Path(args.dir), write=args.write)
