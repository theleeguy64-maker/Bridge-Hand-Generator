"""Tests for bridge_engine.rotate_profile."""

from __future__ import annotations

import copy

import pytest

from bridge_engine.rotate_profile import ROTATE_MAP, _rotate_seat, rotate_profile


def test_rotate_seat_map():
    assert ROTATE_MAP == {"W": "N", "N": "E", "E": "S", "S": "W"}
    assert _rotate_seat("W") == "N"
    assert _rotate_seat("N") == "E"
    assert _rotate_seat("E") == "S"
    assert _rotate_seat("S") == "W"


def test_rotate_seat_rejects_bad_input():
    with pytest.raises(ValueError):
        _rotate_seat("X")
    with pytest.raises(ValueError):
        _rotate_seat("")


def test_fixture_factory_returns_independent_dicts(make_profile_dict):
    a = make_profile_dict()
    b = make_profile_dict()
    a["dealer"] = "X"
    assert b["dealer"] == "W"


def test_input_dict_not_mutated(make_profile_dict):
    d = make_profile_dict()
    snapshot = copy.deepcopy(d)
    rotate_profile(d)
    assert d == snapshot


def test_dealer_rotated(make_profile_dict):
    out = rotate_profile(make_profile_dict())
    assert out["dealer"] == "N"  # source W → N


def test_hand_dealing_order_rotated(make_profile_dict):
    out = rotate_profile(make_profile_dict())
    assert out["hand_dealing_order"] == ["N", "E", "S", "W"]  # element-wise


def test_version_reset_to_0_1(make_profile_dict):
    out = rotate_profile(make_profile_dict())
    assert out["version"] == "0.1"


def test_unchanged_top_level_fields(make_profile_dict):
    src = make_profile_dict()
    out = rotate_profile(src)
    for key in (
        "description",
        "category",
        "author",
        "tag",
        "schema_version",
        "sort_order",
        "rotate_deals_by_default",
        "is_invariants_safety_profile",
    ):
        assert out[key] == src[key], f"{key} unexpectedly changed"
