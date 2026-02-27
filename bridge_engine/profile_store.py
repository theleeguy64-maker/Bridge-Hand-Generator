# file: bridge_engine/profile_store.py
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .hand_profile import CATEGORY_DISPLAY_ORDER, HandProfile, ProfileError

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


def list_drafts(profiles_dir: Path) -> List[Path]:
    """
    Return all draft *_TEST.json files in the given profiles directory.
    """
    if not profiles_dir.is_dir():
        return []
    return sorted(p for p in profiles_dir.glob("*_TEST.json") if p.is_file())


def _with_test_suffix(name: str) -> str:
    base = (name or "").strip()
    return base if base.endswith(TEST_NAME_SUFFIX) else base + TEST_NAME_SUFFIX


def _strip_test_suffix(name: str) -> str:
    base = (name or "").strip()
    if base.endswith(TEST_NAME_SUFFIX):
        return base[: -len(TEST_NAME_SUFFIX)].rstrip()
    return base


def _atomic_write(path: Path, content: str) -> None:
    """
    Write content to path atomically: write to a temp file in the same
    directory, then rename.  If the process dies mid-write, the original
    file stays intact (rename is atomic on the same filesystem).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp", prefix=path.stem + "_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        # os.replace is atomic on POSIX and Windows.
        os.replace(tmp, str(path))
    except BaseException:
        # os.fdopen took ownership of fd, so it's already closed.
        Path(tmp).unlink(missing_ok=True)
        raise


def _save_profile_to_path(profile: HandProfile, path: Path) -> None:
    """
    Backwards-compat helper (tests call this).
    Saves profile JSON to the given path.

    IMPORTANT:
      - canonical save must strip trailing ' TEST' from metadata profile_name
      - draft saving is handled elsewhere (autosave_profile_draft)
    """
    data: Dict[str, Any] = profile.to_dict()

    data["profile_name"] = _strip_test_suffix(str(data.get("profile_name", "") or ""))

    _atomic_write(path, json.dumps(data, indent=2, sort_keys=True) + "\n")


def _profile_path_for(profile: HandProfile, base_dir: Path | None = None) -> Path:
    """
    Canonical JSON path for a profile.

    IMPORTANT: canonical filename is derived from the stripped name (no trailing " TEST").
    """
    profiles_dir = _profiles_dir(base_dir)
    base_name = _strip_test_suffix(profile.profile_name or "UNNAMED")
    safe_name = _slugify(base_name)
    version = profile.version or "0.1"
    return profiles_dir / f"{safe_name}_v{version}.json"


# ---------------------------------------------------------------------------
# Load / save
# ---------------------------------------------------------------------------


def _load_profiles(base_dir: Path | None = None) -> List[Tuple[Path, HandProfile]]:
    """
    Load all canonical profiles (exclude *_TEST.json drafts) from disk.

    Skips files that fail to parse or construct, printing a warning to
    stderr so one corrupted file doesn't crash the entire profile list.

    Returns: list of (path, HandProfile)
    """
    profiles: List[Tuple[Path, HandProfile]] = []
    dir_path = _profiles_dir(base_dir)

    for json_path in sorted(dir_path.glob("*.json")):
        if is_draft_path(json_path):
            continue

        try:
            raw = json.loads(json_path.read_text(encoding="utf-8"))
            profile = HandProfile.from_dict(raw)
            profiles.append((json_path, profile))
        except (json.JSONDecodeError, TypeError, KeyError, ValueError, ProfileError) as exc:
            print(
                f"WARNING: Failed to load profile from {json_path}: {exc}",
                file=sys.stderr,
            )

    return profiles


# Public alias (some code paths may prefer the non-underscored name)
def load_profiles(base_dir: Path | None = None) -> List[Tuple[Path, HandProfile]]:
    return _load_profiles(base_dir=base_dir)


def save_profile(profile: HandProfile, base_dir: Path | None = None) -> Path:
    """
    Save profile to its canonical path. Returns the saved path.
    """
    path = _profile_path_for(profile, base_dir=base_dir)
    _save_profile_to_path(profile, path)
    return path


def find_profile_by_name(target_name: str, base_dir: Path | None = None) -> Optional[Tuple[Path, HandProfile]]:
    """
    Find by profile_name (ignoring any trailing " TEST" in metadata).
    """
    want = _strip_test_suffix(target_name or "")
    for path, profile in _load_profiles(base_dir=base_dir):
        have = _strip_test_suffix(profile.profile_name or "")
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

    payload: Dict[str, Any] = profile.to_dict()
    payload["profile_name"] = _with_test_suffix(str(payload.get("profile_name", "") or ""))

    _atomic_write(draft_path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return draft_path


def autosave_profile_draft_for_new(profile: HandProfile, base_dir: Path | None = None) -> Path:
    """
    Autosave a brand-new profile to a *_TEST.json draft path.

    Draft metadata rule:
      - Draft JSON must have profile_name ending with " TEST"
      - Canonical filename is derived from the stripped name (no " TEST")
    """
    canonical = _profile_path_for(profile, base_dir)
    return autosave_profile_draft(profile, canonical)


# ---------------------------------------------------------------------------
# Display ordering
# ---------------------------------------------------------------------------


def _version_sort_key(version_str: str) -> Tuple[float, str]:
    """Parse version for sorting: numeric part descending, then alpha ascending."""
    try:
        return (-float(version_str), version_str)
    except (ValueError, TypeError):
        return (0.0, version_str)


def build_profile_display_map(
    profiles: List[Tuple[Path, HandProfile]],
) -> Dict[int, Tuple[Path, HandProfile]]:
    """
    Build a mapping from display number → (path, profile), grouped by category.

    Profiles are grouped by category in CATEGORY_DISPLAY_ORDER, then within
    each category sorted by version (highest first) then name (alphabetically).

    Profiles with a sort_order field use that exact number.
    Profiles without sort_order get sequential numbers starting at 1,
    skipping any numbers already claimed by sort_order profiles.
    """
    # Group profiles by category, preserving CATEGORY_DISPLAY_ORDER.
    by_category: Dict[str, List[Tuple[Path, HandProfile]]] = {}
    for cat in CATEGORY_DISPLAY_ORDER:
        by_category[cat] = []

    for path, profile in profiles:
        cat = profile.category or ""
        if cat not in by_category:
            # Unknown category — treat as uncategorised
            by_category.setdefault("", [])
            by_category[""].append((path, profile))
        else:
            by_category[cat].append((path, profile))

    # Sort within each category: highest version first, then name ascending
    for cat_profiles in by_category.values():
        cat_profiles.sort(
            key=lambda pair: (
                _version_sort_key(pair[1].version),
                pair[1].profile_name.lower(),
            )
        )

    # Build the flat ordering: categories in display order, within each
    # category separate sort_order profiles from sequential ones.
    ordered: List[Tuple[int, Path, HandProfile]] = []
    unordered_flat: List[Tuple[Path, HandProfile]] = []

    for cat in CATEGORY_DISPLAY_ORDER:
        for path, profile in by_category.get(cat, []):
            so = profile.sort_order
            if so is not None:
                ordered.append((so, path, profile))
            else:
                unordered_flat.append((path, profile))

    # Collect claimed numbers from sort_order profiles
    claimed = {so for so, _, _ in ordered}

    # Assign sequential numbers to unordered profiles, skipping claimed
    result: Dict[int, Tuple[Path, HandProfile]] = {}
    seq = 1
    for path, profile in unordered_flat:
        while seq in claimed:
            seq += 1
        result[seq] = (path, profile)
        seq += 1

    # Add ordered profiles at their declared positions
    for so, path, profile in sorted(ordered):
        result[so] = (path, profile)

    return result


def print_profile_display_map(
    display_map: Dict[int, Tuple[Path, HandProfile]],
) -> None:
    """Print the numbered profile list from a display map, grouped by category."""
    # Group display numbers by category, preserving display order.
    cat_nums: Dict[str, List[int]] = {}
    for cat in CATEGORY_DISPLAY_ORDER:
        cat_nums[cat] = []

    for num in sorted(display_map):
        _, profile = display_map[num]
        cat = profile.category or ""
        if cat not in cat_nums:
            cat_nums.setdefault("", [])
            cat_nums[""].append(num)
        else:
            cat_nums[cat].append(num)

    # Print each non-empty category with a header.
    for cat in CATEGORY_DISPLAY_ORDER:
        nums = cat_nums.get(cat, [])
        if not nums:
            continue
        header = cat if cat else "Uncategorised"
        print(f"\n  --- {header} ---")
        for num in nums:
            _, profile = display_map[num]
            version_str = f"v{profile.version}" if profile.version else "(no version)"
            print(f"    {num}) {profile.profile_name} ({version_str})")


def delete_draft_for_canonical(canonical_path: Path) -> None:
    """
    Delete the sibling <stem>_TEST.json draft if present.
    """
    try:
        draft_path = canonical_path.with_name(canonical_path.stem + "_TEST.json")
        if draft_path.exists():
            draft_path.unlink()
    except OSError:
        # best-effort cleanup only — narrow to filesystem errors
        return
