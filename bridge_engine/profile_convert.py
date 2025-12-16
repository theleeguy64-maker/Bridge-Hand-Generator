
import json
from pathlib import Path
from bridge_engine.hand_profile import validate_profile

def convert_profiles(dir_path: Path, write: bool = False):
    for path in dir_path.glob("*.json"):
        data = json.loads(path.read_text())
        profile = validate_profile(data)
        profile.schema_version = 1
        if write:
            path.write_text(json.dumps(profile.to_dict(), indent=2))
        else:
            print(f"Would convert: {path}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", required=True)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    convert_profiles(Path(args.dir), write=args.write)
