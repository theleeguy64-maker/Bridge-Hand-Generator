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
    SeatProfile,
    HandProfile,
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

# New tests for NS role metadata helpers
def test_ns_driver_seat_defaults_to_north(make_valid_profile) -> None:
    """
    If ns_role_mode is not explicitly set, ns_driver_seat()
    should default to North (backwards compatible).
    """
    profile = make_valid_profile()
    # Default ns_role_mode on the model is "north_drives"
    assert profile.ns_driver_seat() == "N"


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
    assert profile.ns_driver_seat() == "N"

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
    profile = make_valid_profile()
    # default on freshly-created profiles
    assert profile.ns_role_mode == "north_drives"
    assert profile.ns_driver_seat() == "N"

    # round-trip via dict
    data = profile.to_dict()
    rebuilt = HandProfile.from_dict(data)
    assert rebuilt.ns_role_mode == "north_drives"
    assert rebuilt.ns_driver_seat() == "N"

def test_ns_role_mode_defaults_for_legacy_dict(make_valid_profile) -> None:
    profile = make_valid_profile()
    data = profile.to_dict()

    # Simulate an old on-disk profile with no ns_role_mode
    data.pop("ns_role_mode", None)
    data["schema_version"] = 0

    validated = validate_profile(data)
    assert validated.ns_role_mode == "north_drives"
    assert validated.ns_driver_seat() == "N"

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

def test_ns_driver_seat_invalid_mode_falls_back_to_n(make_valid_profile) -> None:
    profile = make_valid_profile()
    profile = replace(profile, ns_role_mode="totally_bogus")
    assert profile.ns_driver_seat() == "N"

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

