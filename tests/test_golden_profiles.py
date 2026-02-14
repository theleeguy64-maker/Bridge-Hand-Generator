from __future__ import annotations

from pathlib import Path
from typing import Tuple
import json

import pytest

from bridge_engine import profile_store as ps
from bridge_engine.hand_profile import HandProfile, validate_profile


def _get_profile_entry_by_name(target_name: str) -> Tuple[Path, HandProfile]:
    """
    Helper: use the real profile_store loader to find a profile
    by its profile_name. If it's not present on disk, skip the test.
    """
    entries = ps._load_profiles()  # List[Tuple[Path, HandProfile]] (or similar)
    for path, profile in entries:
        if profile.profile_name == target_name:
            return path, profile

    pytest.skip(f"Golden profile with name {target_name!r} not found on disk.")


def test_golden_defense_to_weak_2s_profile_valid() -> None:
    """
    Golden test: the 'Defense to Weak 2s' profile on disk should
    be structurally valid and keep its expected filename/version.
    """
    expected_name = "Defense to 3 Weak 2s - Multi Overcall Shapes"
    expected_file = "Defense_to_3_Weak_2s_-_Multi_Overcall_Shapes_v0.9.json"

    path, profile = _get_profile_entry_by_name(expected_name)

    # Check we're looking at the right on-disk file
    assert path.name == expected_file

    # Basic sanity on the loaded HandProfile
    assert profile.profile_name == expected_name
    assert profile.dealer in ("N", "E", "S", "W")

    # For full semantic validation, reload raw JSON and let validate_profile
    # construct a proper HandProfile via from_dict.
    raw = json.loads(path.read_text(encoding="utf-8"))
    validate_profile(raw)


def test_golden_ops_interference_over_our_1nt_profile_valid() -> None:
    """
    Golden test: the 'Ops interference over our 1NT' profile should
    be structurally valid and mapped to the expected JSON file.
    """
    expected_name = "Ops interference over our 1NT"
    expected_file = "Ops_interference_over_our_1NT_v0.9.json"

    path, profile = _get_profile_entry_by_name(expected_name)

    # Check filename / version
    assert path.name == expected_file

    # Basic structural expectations using the HandProfile as loaded
    assert profile.profile_name == expected_name
    assert profile.tag in ("Opener", "Overcaller")
    assert profile.dealer in ("N", "E", "S", "W")

    # Full validation: reload as dict so validate_profile() goes through
    # the dict → HandProfile.from_dict(...) path and builds proper SeatProfiles.
    raw = json.loads(path.read_text(encoding="utf-8"))
    validate_profile(raw)