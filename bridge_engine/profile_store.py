# file: bridge_engine/profile_store.py
from __future__ import annotations

import json
from pathlib import Path
from typing import List, Tuple, Optional

from .hand_profile import HandProfile
from .hand_profile_model import HandProfile

PROFILE_DIR_NAME = "profiles"

def profile_path_for_name(profile_name: str, version: str) -> Path:
    """Whatever you currently do to get the canonical JSON path."""
    # existing implementation...
    ...

def test_profile_path_for_canonical(canonical: Path) -> Path:
    """
    Given a canonical profile JSON path, return the corresponding TEST path.

    Example:
      profiles/Foo_Profile_v0.3.json
      -> profiles/Foo_Profile_v0.3_TEST.json
    """
    return canonical.with_name(canonical.stem + "_TEST.json")

def autosave_profile_draft(
    profile: HandProfile,
    canonical_path: Path,
) -> Path:
    """
    Write an autosave draft copy of the profile next to the canonical path.

    - Writes JSON to <stem>_TEST.json
    - Overwrites on each call
    """
    test_path = test_profile_path_for_canonical(canonical_path)
    data = profile.to_dict() if hasattr(profile, "to_dict") else profile.__dict__
    test_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return test_path

def autosave_profile_draft_for_new(profile: HandProfile) -> Path:
    safe_name = _slugify(profile.profile_name or "UNNAMED")  # reuse your existing slugify
    canonical = PROFILES_DIR / f"{safe_name}_v{profile.version or '0.1'}.json"
    return autosave_profile_draft(profile, canonical)

def _profiles_dir(base_dir: Path | None = None) -> Path:
    """
    Return the directory that stores profile JSON files.

    If base_dir is None, use the current working directory.
    Ensures the directory exists.
    """
    if base_dir is None:
        base_dir = Path.cwd()
    dir_path = base_dir / PROFILE_DIR_NAME
    dir_path.mkdir(parents=True, exist_ok=True)
    return dir_path

def _safe_file_stem(name: str) -> str:
    """
    Normalise a profile name into a safe filename stem:
    - replace whitespace with underscores
    - keep only letters, digits, '_', '-', '.'
    """
    name = "_".join(name.split())
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.")
    return "".join(ch for ch in name if ch in allowed)


def _profile_path_for(profile: HandProfile, base_dir: Path | None = None) -> Path:
    """
    Compute the JSON filepath for a given HandProfile using profile_name + version.
    """
    version = profile.version or "noversion"
    stem = _safe_file_stem(profile.profile_name)
    filename = f"{stem}_v{version}.json"
    return _profiles_dir(base_dir) / filename


def _save_profile_to_path(profile: HandProfile, path: Path) -> None:
    """
    Save a HandProfile to JSON at the given path.
    """
    data = profile.to_dict() if hasattr(profile, "to_dict") else profile.__dict__
    path.write_text(json.dumps(data, indent=2))


def _load_profiles(base_dir: Path | None = None) -> List[Tuple[Path, HandProfile]]:
    """
    Load all profiles from disk and return a list of (path, HandProfile).
    """
    profiles: List[Tuple[Path, HandProfile]] = []
    dir_path = _profiles_dir(base_dir)
    for json_path in sorted(dir_path.glob("*.json")):
        raw = json.loads(json_path.read_text())
        # If you have a dedicated constructor, use it here. For now,
        # we assume HandProfile(**raw) works with your dataclass.
        profile = HandProfile(**raw)
        profiles.append((json_path, profile))
    return profiles