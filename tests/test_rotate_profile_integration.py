"""Integration tests: rotate real profile files from profiles/."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bridge_engine.hand_profile_model import HandProfile
from bridge_engine.hand_profile_validate import validate_profile
from bridge_engine.rotate_profile import rotate_profile


REAL_TARGET_PROFILES = [
    "Opps_Open_3_Weak_2s_and_we_Compete_v1.0.json",
    "Opps_Open_Strong_1NT_and_we_Overcall_Cappeletti_v1.0.json",
    "Opps_Open_&_Our_TO_Dbl_v0.9.json",
    "Opps_Open_&_Our_TO_Dbl_Balancing_v0.9.json",
]


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("filename", REAL_TARGET_PROFILES)
def test_rotate_each_real_profile(filename, tmp_path):
    src_path = _project_root() / "profiles" / filename
    if not src_path.exists():
        pytest.skip(f"{filename} not present in profiles/")

    src_dict = json.loads(src_path.read_text(encoding="utf-8"))
    rotated = rotate_profile(src_dict)
    rotated["rotated_from"] = src_path.name

    profile = HandProfile.from_dict(rotated)
    validate_profile(profile)

    # Sanity: dealer rotated, version reset, name swapped.
    assert rotated["dealer"] != src_dict["dealer"]
    assert rotated["version"] == "0.1"
    assert "Opps" not in rotated["profile_name"] or "We" in rotated["profile_name"]
