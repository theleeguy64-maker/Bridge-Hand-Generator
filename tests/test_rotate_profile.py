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


def test_seat_profiles_rekeyed(make_profile_dict):
    src = make_profile_dict()
    out = rotate_profile(src)
    # Source had keys N/E/S/W; each rotates.
    assert set(out["seat_profiles"].keys()) == {"N", "E", "S", "W"}
    # Source W's seat-profile content (its subprofiles) ends up under N.
    src_w = src["seat_profiles"]["W"]
    out_n = out["seat_profiles"]["N"]
    assert out_n["seat"] == "N"  # inner seat field rotated
    # subprofile bodies preserved here; rotation of contingents tested separately
    assert out_n["subprofiles"] == src_w["subprofiles"]
    # Same check for N → E.
    assert out["seat_profiles"]["E"]["seat"] == "E"


def test_subprofile_exclusions_rotated(make_profile_dict):
    out = rotate_profile(make_profile_dict())
    # Source had W and E exclusion seats → N and S.
    seats = sorted(e["seat"] for e in out["subprofile_exclusions"])
    assert seats == ["N", "S"]
    # Subprofile indices unchanged.
    indices = sorted(e["subprofile_index"] for e in out["subprofile_exclusions"])
    assert indices == [1, 2]


def test_legacy_fields_stripped(make_profile_dict):
    src = make_profile_dict()
    src["ns_role_mode"] = "stale"
    src["ew_role_mode"] = "stale"
    src["ns_bespoke_map"] = {"1": "stale"}
    src["ew_bespoke_map"] = {"1": "stale"}
    out = rotate_profile(src)
    for key in ("ns_role_mode", "ew_role_mode", "ns_bespoke_map", "ew_bespoke_map"):
        assert key not in out, f"{key} should have been stripped"


def test_unknown_top_level_keys_passthrough(make_profile_dict):
    src = make_profile_dict()
    src["custom_extension"] = {"author_note": "hi"}
    src["future_flag"] = 42
    out = rotate_profile(src)
    assert out["custom_extension"] == {"author_note": "hi"}
    assert out["future_flag"] == 42


def test_subprofile_partner_contingent_seat_rotated(make_profile_dict):
    out = rotate_profile(make_profile_dict())
    # Source: N's subprofile had partner_seat="S". After rotation, that subprofile
    # lives at E (N→E), and partner_seat S→W.
    sub = out["seat_profiles"]["E"]["subprofiles"][0]
    assert sub["partner_contingent_constraint"]["partner_seat"] == "W"


def test_subprofile_opponent_contingent_seat_rotated(make_profile_dict):
    out = rotate_profile(make_profile_dict())
    # Source: E's subprofile had opponent_seat="W". After rotation, that subprofile
    # lives at S (E→S), and opponent_seat W→N.
    sub = out["seat_profiles"]["S"]["subprofiles"][0]
    assert sub["opponents_contingent_suit_constraint"]["opponent_seat"] == "N"


def test_subprofile_without_contingents_unchanged(make_profile_dict):
    src = make_profile_dict()
    out = rotate_profile(src)
    # Source: S's subprofile had no contingents (only N and E did).
    # After rotation it lives at W. Both contingent fields stay None.
    sub = out["seat_profiles"]["W"]["subprofiles"][0]
    assert sub["partner_contingent_constraint"] is None
    assert sub["opponents_contingent_suit_constraint"] is None


def test_linked_profiles_swap_ns_ew(make_profile_dict):
    src = make_profile_dict()
    out = rotate_profile(src)
    # Source ns had primary N (rotates to E, lives in EW slot now).
    assert out["ew_linked_profile"]["primary_seat"] == "E"
    # Source ew had primary E (rotates to S, lives in NS slot now).
    assert out["ns_linked_profile"]["primary_seat"] == "S"
    # subprofile_map (index-keyed) byte-identical.
    assert out["ew_linked_profile"]["subprofile_map"] == src["ns_linked_profile"]["subprofile_map"]
    assert out["ns_linked_profile"]["subprofile_map"] == src["ew_linked_profile"]["subprofile_map"]


def test_linked_profile_one_none_handled(make_profile_dict):
    src = make_profile_dict()
    src["ew_linked_profile"] = None
    out = rotate_profile(src)
    # Source ns moves to ew slot with primary rotated; ns slot becomes None.
    assert out["ew_linked_profile"] is not None
    assert out["ew_linked_profile"]["primary_seat"] == "E"
    assert out["ns_linked_profile"] is None


def test_linked_profile_both_none_handled(make_profile_dict):
    src = make_profile_dict()
    src["ns_linked_profile"] = None
    src["ew_linked_profile"] = None
    out = rotate_profile(src)
    assert out["ns_linked_profile"] is None
    assert out["ew_linked_profile"] is None
