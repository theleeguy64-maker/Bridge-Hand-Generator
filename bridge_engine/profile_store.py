# file: bridge_engine/profile_store.py
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .hand_profile import HandProfile

PROFILE_DIR_NAME = "profiles"
TEST_NAME_SUFFIX = " TEST"


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _project_root() -> Path:
    # bridge_engine/ -> project root (Exec/)
    return Path(__file__).resolve().parents[1]


def _profiles_dir(base_dir: Path | None = None) -> Path:
    """
    Return the profiles/ directory, creating it if missing.

    Tests rely on this creating the directory for custom tmp_path bases.
    """
    root = base_dir if base_dir is not None else _project_root()
    p = root / PROFILE_DIR_NAME
    p.mkdir(parents=True, exist_ok=True)
    return p


def _slugify(name: str) -> str:
    """
    Turn a human-friendly profile name into a stable filename stem.

    Examples:
      "Defense to 3 Weak 2s" -> "Defense_to_3_Weak_2s"
      "Opps_Open_&_Our_TO_Dbl" -> "Opps_Open_Our_TO_Dbl"
    """
    s = (name or "").strip()

    # Convert any non-alnum runs to underscores (keep underscores)
    s = re.sub(r"[^\w]+", "_", s, flags=re.UNICODE)

    # Collapse underscores and trim
    s = re.sub(r"_+", "_", s).strip("_")

    return s or "UNNAMED"


def is_draft_path(path: Path) -> bool:
    return path.name.endswith("_TEST.json")


def _with_test_suffix(name: str) -> str:
    base = (name or "").rstrip()
    return base if base.endswith(TEST_NAME_SUFFIX) else (base + TEST_NAME_SUFFIX).strip()


def _strip_test_suffix(name: str) -> str:
    base = (name or "").rstrip()
    if base.endswith(TEST_NAME_SUFFIX):
        return base[: -len(TEST_NAME_SUFFIX)].rstrip()
    return base

def _save_profile_to_path(profile: HandProfile, path: Path) -> None:
    """
    Backwards-compat helper (tests call this).
    Saves profile JSON to the given path.

    IMPORTANT:
      - canonical save must strip trailing ' TEST' from metadata profile_name
      - draft saving is handled elsewhere (autosave_profile_draft)
    """
    data: Dict[str, Any] = (
        profile.to_dict() if hasattr(profile, "to_dict") else dict(profile.__dict__)
    )

    name = str(data.get("profile_name") or "")
    if name.endswith(" TEST"):
        data["profile_name"] = name[:-5].rstrip()

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")

def _profile_path_for(profile: HandProfile, base_dir: Path | None = None) -> Path:
    """
    Canonical JSON path for a profile.

    IMPORTANT: canonical filename is derived from the stripped name (no trailing " TEST").
    """
    profiles_dir = _profiles_dir(base_dir)
    base_name = _strip_test_suffix(getattr(profile, "profile_name", "") or "UNNAMED")
    safe_name = _slugify(base_name)
    version = getattr(profile, "version", "") or "0.1"
    return profiles_dir / f"{safe_name}_v{version}.json"


# ---------------------------------------------------------------------------
# Load / save
# ---------------------------------------------------------------------------

def _load_profiles(base_dir: Path | None = None) -> List[Tuple[Path, HandProfile]]:
    """
    Load all canonical profiles (exclude *_TEST.json drafts) from disk.

    Returns: list of (path, HandProfile)
    """
    profiles: List[Tuple[Path, HandProfile]] = []
    dir_path = _profiles_dir(base_dir)

    for json_path in sorted(dir_path.glob("*.json")):
        if is_draft_path(json_path):
            continue

        raw = json.loads(json_path.read_text(encoding="utf-8"))
        profile = HandProfile(**raw)
        profiles.append((json_path, profile))

    return profiles


# Public alias (some code paths may prefer the non-underscored name)
def load_profiles(base_dir: Path | None = None) -> List[Tuple[Path, HandProfile]]:
    return _load_profiles(base_dir=base_dir)


def save_profile(profile: HandProfile, base_dir: Path | None = None) -> Path:
    """
    Save profile to its canonical path. Returns the saved path.
    """
    path = _profile_path_for(profile, base_dir=base_dir)
    data: Dict[str, Any] = profile.to_dict() if hasattr(profile, "to_dict") else dict(profile.__dict__)

    # Canonical metadata should NOT carry the " TEST" suffix.
    data["profile_name"] = _strip_test_suffix(str(data.get("profile_name", "") or ""))

    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def find_profile_by_name(target_name: str, base_dir: Path | None = None) -> Optional[Tuple[Path, HandProfile]]:
    """
    Find by profile_name (ignoring any trailing " TEST" in metadata).
    """
    want = _strip_test_suffix(target_name or "")
    for path, profile in _load_profiles(base_dir=base_dir):
        have = _strip_test_suffix(getattr(profile, "profile_name", "") or "")
        if have == want:
            return (path, profile)
    return None


# ---------------------------------------------------------------------------
# Draft autosave helpers
# ---------------------------------------------------------------------------

def autosave_profile_draft(profile: HandProfile, canonical_path: Path) -> Path:
    """
    Write an autosave draft copy of the profile next to the canonical path.

    - Writes JSON to <canonical_stem>_TEST.json
    - Ensures JSON metadata profile_name ends with " TEST"
      (does NOT mutate the in-memory HandProfile object)
    """
    draft_path = canonical_path.with_name(canonical_path.stem + "_TEST.json")

    payload: Dict[str, Any] = profile.to_dict() if hasattr(profile, "to_dict") else dict(profile.__dict__)
    payload["profile_name"] = _with_test_suffix(str(payload.get("profile_name", "") or ""))

    draft_path.parent.mkdir(parents=True, exist_ok=True)
    draft_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return draft_path


def autosave_profile_draft_for_new(profile: HandProfile, base_dir: Path | None = None) -> Path:
    """
    Autosave a brand-new profile to a *_TEST.json draft path.

    Draft metadata rule:
      - Draft JSON must have profile_name ending with " TEST"
      - Canonical filename is derived from the stripped name (no " TEST")
    """
    profiles_dir = _profiles_dir(base_dir)

    base_name = _strip_test_suffix(getattr(profile, "profile_name", "") or "UNNAMED")
    safe_name = _slugify(base_name)
    version = getattr(profile, "version", "") or "0.1"
    canonical = profiles_dir / f"{safe_name}_v{version}.json"

    return autosave_profile_draft(profile, canonical)


def delete_draft_for_canonical(canonical_path: Path) -> None:
    """
    Delete the sibling <stem>_TEST.json draft if present.
    """
    try:
        draft_path = canonical_path.with_name(canonical_path.stem + "_TEST.json")
        if draft_path.exists():
            draft_path.unlink()
    except Exception:
        # best-effort cleanup only
        return
