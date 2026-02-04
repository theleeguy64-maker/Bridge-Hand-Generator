"""
Tests for bridge_engine/profile_convert.py

Tests the batch schema migration functionality that converts profiles
from schema_version=0 to schema_version=1.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bridge_engine.profile_convert import convert_profiles


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

def _make_minimal_profile_dict(name: str = "TestProfile") -> dict:
    """
    Create a minimal valid profile dict for testing.
    Uses schema_version=0 to test migration.
    """
    return {
        "profile_name": name,
        "description": "Test profile for conversion",
        "dealer": "N",
        "hand_dealing_order": ["N", "E", "S", "W"],
        "tag": "Opener",  # Must be "Opener" or "Overcaller"
        "author": "Test",
        "version": "1.0",
        "schema_version": 0,  # Old version to be converted
        "rotate_deals_by_default": True,
        "seat_profiles": {
            "N": {
                "seat": "N",
                "subprofiles": [{
                    "standard": {
                        "spades": {"min_cards": 0, "max_cards": 13},
                        "hearts": {"min_cards": 0, "max_cards": 13},
                        "diamonds": {"min_cards": 0, "max_cards": 13},
                        "clubs": {"min_cards": 0, "max_cards": 13},
                    },
                    "weight_percent": 100,
                }],
            },
            "E": {
                "seat": "E",
                "subprofiles": [{
                    "standard": {
                        "spades": {"min_cards": 0, "max_cards": 13},
                        "hearts": {"min_cards": 0, "max_cards": 13},
                        "diamonds": {"min_cards": 0, "max_cards": 13},
                        "clubs": {"min_cards": 0, "max_cards": 13},
                    },
                    "weight_percent": 100,
                }],
            },
            "S": {
                "seat": "S",
                "subprofiles": [{
                    "standard": {
                        "spades": {"min_cards": 0, "max_cards": 13},
                        "hearts": {"min_cards": 0, "max_cards": 13},
                        "diamonds": {"min_cards": 0, "max_cards": 13},
                        "clubs": {"min_cards": 0, "max_cards": 13},
                    },
                    "weight_percent": 100,
                }],
            },
            "W": {
                "seat": "W",
                "subprofiles": [{
                    "standard": {
                        "spades": {"min_cards": 0, "max_cards": 13},
                        "hearts": {"min_cards": 0, "max_cards": 13},
                        "diamonds": {"min_cards": 0, "max_cards": 13},
                        "clubs": {"min_cards": 0, "max_cards": 13},
                    },
                    "weight_percent": 100,
                }],
            },
        },
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_convert_profiles_dry_run(tmp_path: Path, capsys) -> None:
    """write=False should not modify files, only print what would be converted."""
    # Create a test profile file
    profile_data = _make_minimal_profile_dict("DryRunProfile")
    profile_path = tmp_path / "test_profile.json"
    profile_path.write_text(json.dumps(profile_data, indent=2))

    # Store original content
    original_content = profile_path.read_text()

    # Run conversion in dry-run mode
    convert_profiles(tmp_path, write=False)

    # Verify file was NOT modified
    assert profile_path.read_text() == original_content

    # Verify output message
    captured = capsys.readouterr()
    assert "Would convert:" in captured.out
    assert "test_profile.json" in captured.out


def test_convert_profiles_writes_v1(tmp_path: Path) -> None:
    """write=True should update schema_version to 1."""
    # Create a test profile file with schema_version=0
    profile_data = _make_minimal_profile_dict("WriteV1Profile")
    assert profile_data["schema_version"] == 0

    profile_path = tmp_path / "test_profile.json"
    profile_path.write_text(json.dumps(profile_data, indent=2))

    # Run conversion with write=True
    convert_profiles(tmp_path, write=True)

    # Read back and verify schema_version changed
    converted_data = json.loads(profile_path.read_text())
    assert converted_data["schema_version"] == 1


def test_convert_profiles_skips_non_json(tmp_path: Path, capsys) -> None:
    """Should only process .json files, ignoring others."""
    # Create a non-JSON file
    txt_file = tmp_path / "readme.txt"
    txt_file.write_text("This is not a JSON file")

    # Create a JSON profile for comparison
    profile_data = _make_minimal_profile_dict("JsonProfile")
    json_file = tmp_path / "profile.json"
    json_file.write_text(json.dumps(profile_data, indent=2))

    # Run conversion
    convert_profiles(tmp_path, write=False)

    # Verify only the JSON file was processed
    captured = capsys.readouterr()
    assert "profile.json" in captured.out
    assert "readme.txt" not in captured.out


def test_convert_profiles_empty_dir(tmp_path: Path, capsys) -> None:
    """Should handle empty directory gracefully."""
    # Run conversion on empty directory
    convert_profiles(tmp_path, write=False)

    # Should complete without error, no output
    captured = capsys.readouterr()
    assert captured.out == ""


def test_convert_profiles_preserves_profile_data(tmp_path: Path) -> None:
    """Converted profile should retain all original data except schema_version."""
    # Create a test profile with specific data
    profile_data = _make_minimal_profile_dict("PreserveDataProfile")
    profile_data["description"] = "Important description to preserve"
    profile_data["author"] = "Test Author"
    profile_data["tag"] = "Overcaller"  # Must be valid tag

    profile_path = tmp_path / "test_profile.json"
    profile_path.write_text(json.dumps(profile_data, indent=2))

    # Run conversion
    convert_profiles(tmp_path, write=True)

    # Read back and verify data preserved
    converted_data = json.loads(profile_path.read_text())

    # Schema version should be updated
    assert converted_data["schema_version"] == 1

    # Other fields should be preserved
    assert converted_data["profile_name"] == "PreserveDataProfile"
    assert converted_data["description"] == "Important description to preserve"
    assert converted_data["author"] == "Test Author"
    assert converted_data["tag"] == "Overcaller"
    assert converted_data["dealer"] == "N"
    assert converted_data["hand_dealing_order"] == ["N", "E", "S", "W"]


def test_convert_profiles_multiple_files(tmp_path: Path) -> None:
    """Should process all JSON files in directory."""
    # Create multiple profile files
    for i in range(3):
        profile_data = _make_minimal_profile_dict(f"Profile{i}")
        profile_path = tmp_path / f"profile_{i}.json"
        profile_path.write_text(json.dumps(profile_data, indent=2))

    # Run conversion
    convert_profiles(tmp_path, write=True)

    # Verify all files were converted
    for i in range(3):
        profile_path = tmp_path / f"profile_{i}.json"
        converted_data = json.loads(profile_path.read_text())
        assert converted_data["schema_version"] == 1
        assert converted_data["profile_name"] == f"Profile{i}"
