"""Tests for bridge_engine.rotate_profile."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from bridge_engine.rotate_profile import ROTATE_MAP, _derived_output_path, _rotate_seat, _swap_pronouns, rotate_profile


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


@pytest.mark.parametrize(
    "source, expected",
    [
        ("Opps Open Strong 1NT and we Overcall Cappeletti", "We Open Strong 1NT and Opps Overcall Cappeletti"),
        ("Opps Open 3 Weak 2s and we Compete", "We Open 3 Weak 2s and Opps Compete"),
        ("Opps Open & Our TO Dbl", "We Open & Opps TO Dbl"),
        ("Opps Open & Our TO Dbl Balancing", "We Open & Opps TO Dbl Balancing"),
    ],
)
def test_swap_pronouns(source, expected):
    assert _swap_pronouns(source) == expected


def test_swap_pronouns_no_pronouns_returns_unchanged():
    # Returns the input verbatim; the rotate_profile() wrapper raises.
    assert _swap_pronouns("Big Hands") == "Big Hands"


def test_rotate_profile_default_name_uses_swap(make_profile_dict):
    src = make_profile_dict()
    src["profile_name"] = "Opps Open 1NT and we Overcall"
    out = rotate_profile(src)
    assert out["profile_name"] == "We Open 1NT and Opps Overcall"


def test_rotate_profile_name_override(make_profile_dict):
    out = rotate_profile(make_profile_dict(), new_name="Custom Name")
    assert out["profile_name"] == "Custom Name"


def test_rotate_profile_description_override(make_profile_dict):
    out = rotate_profile(make_profile_dict(), new_description="Custom desc")
    assert out["description"] == "Custom desc"


def test_rotate_profile_no_pronouns_raises(make_profile_dict):
    src = make_profile_dict()
    src["profile_name"] = "Big Hands"
    from bridge_engine.hand_profile_model import ProfileError

    with pytest.raises(ProfileError, match="Opps/We/Our pronouns"):
        rotate_profile(src)


def test_rotate_profile_already_rotated_refused(make_profile_dict):
    src = make_profile_dict()
    src["rotated_from"] = "earlier.json"
    from bridge_engine.hand_profile_model import ProfileError

    with pytest.raises(ProfileError, match="already a rotated profile"):
        rotate_profile(src)


def test_idempotent_to_full_cycle_seat_fields(make_profile_dict):
    """Four rotations of the seat-bearing fields return to the original."""
    src = make_profile_dict()
    cur = src
    for _ in range(4):
        # Reset profile_name each iteration so the pronoun-swap guard fires
        # only once per cycle. We're testing seat-rotation idempotence here.
        cur = {**cur, "profile_name": src["profile_name"]}
        cur = rotate_profile(cur)
    # After 4 rotations the seat-bearing fields match the source.
    assert cur["dealer"] == src["dealer"]
    assert cur["hand_dealing_order"] == src["hand_dealing_order"]
    assert cur["seat_profiles"].keys() == src["seat_profiles"].keys()
    for seat, sp in src["seat_profiles"].items():
        assert cur["seat_profiles"][seat]["seat"] == sp["seat"]
        assert cur["seat_profiles"][seat]["subprofiles"] == sp["subprofiles"]
    src_excl_sorted = sorted((e["seat"], e["subprofile_index"]) for e in src["subprofile_exclusions"])
    cur_excl_sorted = sorted((e["seat"], e["subprofile_index"]) for e in cur["subprofile_exclusions"])
    assert cur_excl_sorted == src_excl_sorted
    # Linked profiles return to their original NS/EW positions and primary_seats.
    assert cur["ns_linked_profile"]["primary_seat"] == src["ns_linked_profile"]["primary_seat"]
    assert cur["ew_linked_profile"]["primary_seat"] == src["ew_linked_profile"]["primary_seat"]


def test_derived_output_path(tmp_path):
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    out = _derived_output_path("We Open 1NT and Opps Overcall", profiles_dir)
    assert out == profiles_dir / "We_Open_1NT_and_Opps_Overcall_v0.1.json"


def test_derived_output_path_preserves_ampersand(tmp_path):
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    out = _derived_output_path("We Open & Opps TO Dbl", profiles_dir)
    assert out.name == "We_Open_&_Opps_TO_Dbl_v0.1.json"
