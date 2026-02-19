from __future__ import annotations
from dataclasses import replace

import pytest
import random

from bridge_engine.hand_profile import (
    SuitRange,
    StandardSuitConstraints,
    RandomSuitConstraintData,
    PartnerContingentData,
    SuitPairOverride,
    SubProfile,
    sub_label,
    SeatProfile,
    HandProfile,
    SubprofileExclusionClause,
    SubprofileExclusionData,
    validate_profile,
    ProfileError,
)


def _standard_all_open() -> StandardSuitConstraints:
    """
    Helper: completely open StandardSuitConstraints.

    Relies on SuitRange() defaults being a fully-open range,
    and on StandardSuitConstraints providing sensible defaults
    for total_min_hcp / total_max_hcp.
    """
    r = SuitRange()
    return StandardSuitConstraints(
        spades=r,
        hearts=r,
        diamonds=r,
        clubs=r,
    )


# ---------------------------------------------------------------------------
# SuitRange tests
# ---------------------------------------------------------------------------


def test_suit_range_invalid_cards_raises() -> None:
    # min_cards > max_cards should raise at construction time
    with pytest.raises(ProfileError):
        SuitRange(min_cards=10, max_cards=2)


def test_suit_range_invalid_hcp_range_raises() -> None:
    # min_hcp > max_hcp should raise at construction time
    with pytest.raises(ProfileError):
        SuitRange(min_hcp=10, max_hcp=5)


# ---------------------------------------------------------------------------
# Random suit / pair overrides / partner-contingent tests
# ---------------------------------------------------------------------------


def test_suit_pair_override_constructs_with_valid_data() -> None:
    """
    Basic sanity: SuitPairOverride can be constructed with valid suits
    and two SuitRange objects without raising.
    """
    spo = SuitPairOverride(
        suits=["S", "H"],
        first_range=SuitRange(),
        second_range=SuitRange(),
    )
    assert spo.suits == ["S", "H"]


def test_partner_must_be_dealt_before_partner_contingent() -> None:
    """
    East has Random Suit, West is Partner Contingent,
    but dealing order is W,E,S,N (invalid because partner seat E
    is dealt after W).
    """
    rs = RandomSuitConstraintData(
        required_suits_count=1,
        allowed_suits=["S"],
        suit_ranges=[SuitRange()],
    )

    north = SeatProfile(seat="N", subprofiles=[SubProfile(_standard_all_open())])
    east = SeatProfile(
        seat="E",
        subprofiles=[SubProfile(_standard_all_open(), random_suit_constraint=rs)],
    )
    south = SeatProfile(seat="S", subprofiles=[SubProfile(_standard_all_open())])
    west = SeatProfile(
        seat="W",
        subprofiles=[
            SubProfile(
                standard=_standard_all_open(),
                partner_contingent_constraint=PartnerContingentData(
                    partner_seat="E",
                    suit_range=SuitRange(),
                ),
            )
        ],
    )

    profile = HandProfile(
        profile_name="TestProfileOrder",
        description="Bad dealing order",
        dealer="W",
        hand_dealing_order=["W", "E", "S", "N"],  # W before E
        tag="Overcaller",
        seat_profiles={"N": north, "E": east, "S": south, "W": west},
    )

    with pytest.raises(ProfileError):
        validate_profile(profile)


# ---------------------------------------------------------------------------
# A reusable “minimal valid” profile
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# validate_profile / constraint tests
# ---------------------------------------------------------------------------


def test_validate_profile_valid(make_valid_profile) -> None:
    """Baseline: the constructed minimal profile should be valid."""
    profile = make_valid_profile()
    validate_profile(profile)  # should not raise


def test_standard_constraints_bad_total_hcp_range_raises() -> None:
    """
    StandardSuitConstraints with total_min_hcp > total_max_hcp
    should raise ProfileError at construction time.
    """
    with pytest.raises(ProfileError):
        StandardSuitConstraints(
            spades=SuitRange(),
            hearts=SuitRange(),
            diamonds=SuitRange(),
            clubs=SuitRange(),
            total_min_hcp=20,
            total_max_hcp=10,
        )


def test_ns_driver_seat_defaults_to_no_driver(make_valid_profile) -> None:
    """
    If ns_role_mode is not explicitly set in legacy data, we treat it as
    'no_driver_no_index' and ns_driver_seat() returns None.
    """
    profile = make_valid_profile()
    assert profile.ns_role_mode == "no_driver_no_index"
    assert profile.ns_driver_seat() is None


def test_ns_driver_seat_respects_ns_role_mode(make_valid_profile) -> None:
    """
    ns_driver_seat() should reflect ns_role_mode when explicitly set.
    """
    profile = make_valid_profile()

    # South drives → S
    profile.ns_role_mode = "south_drives"
    assert profile.ns_driver_seat() == "S"

    # North drives → N
    profile.ns_role_mode = "north_drives"
    assert profile.ns_driver_seat() == "N"

    # Any unknown / future value should safely fall back to North
    profile.ns_role_mode = "something_weird"
    assert profile.ns_driver_seat() is None


def test_ns_role_buckets_all_neutral_for_legacy_profiles(make_valid_profile) -> None:
    """
    For existing profiles (no ns_role_for_seat metadata),
    ns_role_buckets() should classify all N/S subprofiles as neutral.
    """
    profile = make_valid_profile()

    buckets = profile.ns_role_buckets()

    for seat in ("N", "S"):
        seat_buckets = buckets.get(seat)
        # We expect a bucket entry for each NS seat
        assert seat_buckets is not None
        assert seat_buckets["driver"] == []
        assert seat_buckets["follower"] == []
        # Legacy profiles should still have at least one neutral subprofile
        assert len(seat_buckets["neutral"]) >= 1


def test_ns_role_mode_default_and_roundtrip(make_valid_profile) -> None:
    """
    For freshly-created profiles, ns_role_mode should default to
    'no_driver_no_index', and at the metadata level that means
    ns_driver_seat() returns None (no fixed NS driver).

    A to_dict / from_dict round-trip must preserve both the mode
    string and the ns_driver_seat() behaviour.
    """
    profile = make_valid_profile()

    # Default on freshly-created profiles
    assert profile.ns_role_mode == "no_driver_no_index"
    assert profile.ns_driver_seat() is None

    # Round-trip via to_dict / from_dict
    raw = profile.to_dict()
    rebuilt = HandProfile.from_dict(raw)

    assert rebuilt.ns_role_mode == "no_driver_no_index"
    assert rebuilt.ns_driver_seat() is None


def test_ns_role_mode_defaults_for_legacy_dict(make_valid_profile) -> None:
    """
    If a legacy dict has no ns_role_mode key, HandProfile.from_dict()
    should treat it as 'no_driver_no_index'.
    """
    profile = make_valid_profile()
    raw = profile.to_dict()
    raw.pop("ns_role_mode", None)

    restored = HandProfile.from_dict(raw)
    assert restored.ns_role_mode == "no_driver_no_index"


def test_ns_driver_seat_south_drives(make_valid_profile) -> None:
    profile = make_valid_profile()
    profile = replace(profile, ns_role_mode="south_drives")
    assert profile.ns_driver_seat() == "S"


def test_ns_driver_seat_random_driver_only_ns(make_valid_profile) -> None:
    profile = make_valid_profile()
    profile = replace(profile, ns_role_mode="random_driver")

    rng = random.Random(12345)
    for _ in range(20):
        seat = profile.ns_driver_seat(rng)
        assert seat in ("N", "S")


def test_ns_driver_seat_invalid_mode_falls_back_to_none(make_valid_profile) -> None:
    """
    Unknown ns_role_mode values should be treated as 'no driver' at metadata level.
    """
    profile = make_valid_profile()
    profile = replace(profile, ns_role_mode="totally_bogus")

    assert profile.ns_driver_seat() is None


def test_rotate_default_on_new_profile_is_true(make_valid_profile) -> None:
    """
    New profiles should default rotate_deals_by_default to True.
    (This uses whatever make_valid_profile already returns.)
    """
    profile = make_valid_profile()
    assert getattr(profile, "rotate_deals_by_default", True) is True


def test_rotate_default_round_trip_via_dict(make_valid_profile) -> None:
    """
    rotate_deals_by_default should survive a to_dict / from_dict round-trip.
    """
    profile = make_valid_profile()
    # Flip it to False so we can see the change persist:
    profile.rotate_deals_by_default = False

    data = profile.to_dict()
    assert data["rotate_deals_by_default"] is False

    round_tripped = HandProfile.from_dict(data)
    assert round_tripped.rotate_deals_by_default is False


def test_rotate_default_missing_key_defaults_to_true(make_valid_profile) -> None:
    """
    Old JSON that omits rotate_deals_by_default should still load with True.
    """
    profile = make_valid_profile()
    data = profile.to_dict()

    # Simulate an older JSON file without this field
    data.pop("rotate_deals_by_default", None)

    loaded = HandProfile.from_dict(data)
    # When the key is missing, we expect a default of True
    assert loaded.rotate_deals_by_default is True


# ===================================================================
# SubprofileExclusionClause / SubprofileExclusionData serialization
# ===================================================================


def test_exclusion_clause_round_trip() -> None:
    """SubprofileExclusionClause round-trips through to_dict / from_dict."""
    clause = SubprofileExclusionClause(group="MAJOR", length_eq=5, count=2)
    d = clause.to_dict()
    restored = SubprofileExclusionClause.from_dict(d)
    assert restored == clause
    assert d == {"group": "MAJOR", "length_eq": 5, "count": 2}


def test_exclusion_clause_is_frozen() -> None:
    """SubprofileExclusionClause is frozen (immutable)."""
    clause = SubprofileExclusionClause(group="ANY", length_eq=3, count=1)
    with pytest.raises(AttributeError):
        clause.group = "MINOR"  # type: ignore[misc]


def test_exclusion_data_round_trip_with_shapes() -> None:
    """SubprofileExclusionData with excluded_shapes round-trips."""
    exc = SubprofileExclusionData(
        seat="N",
        subprofile_index=1,
        excluded_shapes=["5332", "4432"],
    )
    d = exc.to_dict()
    restored = SubprofileExclusionData.from_dict(d)
    assert restored.seat == "N"
    assert restored.subprofile_index == 1
    assert restored.excluded_shapes == ["5332", "4432"]
    assert restored.clauses is None


def test_exclusion_data_round_trip_with_clauses() -> None:
    """SubprofileExclusionData with clauses round-trips."""
    exc = SubprofileExclusionData(
        seat="S",
        subprofile_index=2,
        clauses=[
            SubprofileExclusionClause(group="ANY", length_eq=6, count=1),
            SubprofileExclusionClause(group="MINOR", length_eq=4, count=2),
        ],
    )
    d = exc.to_dict()
    restored = SubprofileExclusionData.from_dict(d)
    assert restored.seat == "S"
    assert restored.subprofile_index == 2
    assert restored.excluded_shapes is None
    assert len(restored.clauses) == 2
    assert restored.clauses[0].group == "ANY"
    assert restored.clauses[1].group == "MINOR"


def test_exclusion_data_omits_none_fields() -> None:
    """to_dict() omits excluded_shapes and clauses when they are None."""
    exc = SubprofileExclusionData(seat="E", subprofile_index=1)
    d = exc.to_dict()
    assert "excluded_shapes" not in d
    assert "clauses" not in d
    assert d == {"seat": "E", "subprofile_index": 1}


def test_profile_round_trip_with_exclusions(make_valid_profile) -> None:
    """HandProfile with non-empty exclusions survives to_dict / from_dict."""
    profile = make_valid_profile()
    exclusions = [
        SubprofileExclusionData(
            seat="N",
            subprofile_index=1,
            excluded_shapes=["5332"],
        ),
    ]
    # Build a new profile with exclusions.
    data = profile.to_dict()
    data["subprofile_exclusions"] = [e.to_dict() for e in exclusions]
    loaded = HandProfile.from_dict(data)

    assert len(loaded.subprofile_exclusions) == 1
    assert loaded.subprofile_exclusions[0].seat == "N"
    assert loaded.subprofile_exclusions[0].excluded_shapes == ["5332"]

    # Round-trip again to verify to_dict works on loaded profile.
    data2 = loaded.to_dict()
    loaded2 = HandProfile.from_dict(data2)
    assert len(loaded2.subprofile_exclusions) == 1
    assert loaded2.subprofile_exclusions[0].seat == "N"


def test_exclusion_validate_catches_bad_subprofile_index(make_valid_profile) -> None:
    """validate() correctly checks subprofile_index against seat's subprofile count."""
    profile = make_valid_profile()
    # Index 99 should be out of range (each seat has 1 subprofile).
    exc = SubprofileExclusionData(
        seat="N",
        subprofile_index=99,
        excluded_shapes=["5332"],
    )
    with pytest.raises(ProfileError, match="Invalid subprofile index"):
        exc.validate(profile)


# ---------------------------------------------------------------------------
# SubProfile name field + sub_label helper
# ---------------------------------------------------------------------------


def test_subprofile_name_round_trip() -> None:
    """SubProfile.name survives to_dict → from_dict."""
    sub = SubProfile(standard=_standard_all_open(), name="Strong opener")
    d = sub.to_dict()
    assert d["name"] == "Strong opener"
    restored = SubProfile.from_dict(d)
    assert restored.name == "Strong opener"


def test_subprofile_name_none_omitted() -> None:
    """When name is None, to_dict() should not include a 'name' key."""
    sub = SubProfile(standard=_standard_all_open())
    d = sub.to_dict()
    assert "name" not in d


def test_subprofile_name_missing_defaults_none() -> None:
    """Backwards compat: from_dict with no 'name' key produces name=None."""
    d = SubProfile(standard=_standard_all_open()).to_dict()
    assert "name" not in d
    restored = SubProfile.from_dict(d)
    assert restored.name is None


def test_subprofile_name_empty_treated_as_none() -> None:
    """Blank/whitespace-only name is normalised to None on load."""
    d = SubProfile(standard=_standard_all_open()).to_dict()
    d["name"] = "   "
    restored = SubProfile.from_dict(d)
    assert restored.name is None


def test_sub_label_with_name() -> None:
    """sub_label includes the name in parentheses when set."""
    sub = SubProfile(standard=_standard_all_open(), name="Weak response")
    assert sub_label(1, sub) == "Sub-profile 1 (Weak response)"


def test_sub_label_without_name() -> None:
    """sub_label shows only the index when name is None."""
    sub = SubProfile(standard=_standard_all_open())
    assert sub_label(2, sub) == "Sub-profile 2"
