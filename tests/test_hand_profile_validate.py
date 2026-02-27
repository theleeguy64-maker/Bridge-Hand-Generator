"""
Tests for bridge_engine/hand_profile_validate.py

Tests the core validation functions used before all deal generation.
These functions normalize profile data and catch structural errors early.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field, fields
from typing import Any, Dict, List, Optional

import pytest

from bridge_engine.hand_profile_validate import (
    _to_raw_dict,
    _extract_seat_names_from_constraint,
    _normalise_subprofile_weights,
    _validate_random_suit_vs_standard,
    validate_profile,
)
from bridge_engine.hand_profile_model import (
    HandProfile,
    SeatProfile,
    SubProfile,
    SuitRange,
    StandardSuitConstraints,
    RandomSuitConstraintData,
    PartnerContingentData,
    ProfileError,
)


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


def _make_standard(
    spade_min=0,
    spade_max=13,
    heart_min=0,
    heart_max=13,
    diamond_min=0,
    diamond_max=13,
    club_min=0,
    club_max=13,
    min_hcp=0,
    max_hcp=37,
) -> StandardSuitConstraints:
    """Helper to create StandardSuitConstraints."""
    return StandardSuitConstraints(
        spades=SuitRange(min_cards=spade_min, max_cards=spade_max),
        hearts=SuitRange(min_cards=heart_min, max_cards=heart_max),
        diamonds=SuitRange(min_cards=diamond_min, max_cards=diamond_max),
        clubs=SuitRange(min_cards=club_min, max_cards=club_max),
        total_min_hcp=min_hcp,
        total_max_hcp=max_hcp,
    )


def _make_subprofile(
    spade_min=0, heart_min=0, diamond_min=0, club_min=0, min_hcp=0, max_hcp=37, weight=0.0, rs_constraint=None
) -> SubProfile:
    """Helper to create SubProfile."""
    return SubProfile(
        standard=_make_standard(
            spade_min=spade_min,
            heart_min=heart_min,
            diamond_min=diamond_min,
            club_min=club_min,
            min_hcp=min_hcp,
            max_hcp=max_hcp,
        ),
        random_suit_constraint=rs_constraint,
        weight_percent=weight,
    )


def _make_minimal_profile_dict(name: str = "TestProfile") -> Dict[str, Any]:
    """Create a minimal valid profile dict for testing."""
    return {
        "profile_name": name,
        "description": "Test profile",
        "dealer": "N",
        "hand_dealing_order": ["N", "E", "S", "W"],
        "tag": "Opener",
        "author": "Test",
        "version": "1.0",
        "schema_version": 1,
        "rotate_deals_by_default": True,
        "ns_role_mode": "no_driver_no_index",
        "subprofile_exclusions": [],
        "seat_profiles": {
            seat: {
                "seat": seat,
                "subprofiles": [
                    {
                        "standard": {
                            "spades": {"min_cards": 0, "max_cards": 13},
                            "hearts": {"min_cards": 0, "max_cards": 13},
                            "diamonds": {"min_cards": 0, "max_cards": 13},
                            "clubs": {"min_cards": 0, "max_cards": 13},
                        },
                        "weight_percent": 100,
                    }
                ],
            }
            for seat in ["N", "E", "S", "W"]
        },
    }


# ---------------------------------------------------------------------------
# Tests for _to_raw_dict
# ---------------------------------------------------------------------------


class TestToRawDict:
    """Tests for _to_raw_dict() function."""

    def test_from_dict_returns_copy(self) -> None:
        """Dict input should return a shallow copy, not the original."""
        original = {"profile_name": "Test", "data": [1, 2, 3]}
        result = _to_raw_dict(original)

        assert result == original
        assert result is not original  # Must be a copy

    def test_from_hand_profile_uses_to_dict(self, make_valid_profile) -> None:
        """HandProfile input should use to_dict() method."""
        profile = make_valid_profile()
        result = _to_raw_dict(profile)

        assert isinstance(result, dict)
        assert result["profile_name"] == profile.profile_name
        assert result["dealer"] == profile.dealer

    def test_rejects_invalid_type(self) -> None:
        """Non-dict, non-HandProfile input should raise TypeError."""
        with pytest.raises(TypeError, match="dict-like object or HandProfile"):
            _to_raw_dict("not a dict")

        with pytest.raises(TypeError, match="dict-like object or HandProfile"):
            _to_raw_dict(12345)

        with pytest.raises(TypeError, match="dict-like object or HandProfile"):
            _to_raw_dict(["a", "list"])

    def test_handles_mapping_like_objects(self) -> None:
        """Mapping-like objects (dict subclasses) should work."""
        from collections import OrderedDict

        data = OrderedDict([("profile_name", "Test"), ("dealer", "N")])
        result = _to_raw_dict(data)

        assert result["profile_name"] == "Test"
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# Tests for _extract_seat_names_from_constraint
# ---------------------------------------------------------------------------


class TestExtractSeatNames:
    """Tests for _extract_seat_names_from_constraint() function."""

    def test_extracts_from_dataclass_single_seat(self) -> None:
        """Should extract seat from dataclass with single seat field."""
        constraint = PartnerContingentData(
            partner_seat="E",
            suit_range=SuitRange(),
        )
        seats = _extract_seat_names_from_constraint(constraint)

        assert "E" in seats

    def test_extracts_from_dataclass_with_list(self) -> None:
        """Should handle dataclass with list of seats."""

        @dataclass
        class MockConstraint:
            opponent_seats: List[str] = field(default_factory=list)

        constraint = MockConstraint(opponent_seats=["E", "W"])
        seats = _extract_seat_names_from_constraint(constraint)

        assert "E" in seats
        assert "W" in seats

    def test_handles_non_dataclass(self) -> None:
        """Should fall back to dir() probing for non-dataclass objects."""

        class MockConstraint:
            def __init__(self):
                self.partner_seat = "S"

        constraint = MockConstraint()
        seats = _extract_seat_names_from_constraint(constraint)

        assert "S" in seats

    def test_returns_empty_for_no_seat_fields(self) -> None:
        """Should return empty list if no seat fields found."""

        @dataclass
        class MockConstraint:
            some_value: int = 42
            another_value: str = "test"

        constraint = MockConstraint()
        seats = _extract_seat_names_from_constraint(constraint)

        assert seats == []


# ---------------------------------------------------------------------------
# Tests for _normalise_subprofile_weights
# ---------------------------------------------------------------------------


class TestNormaliseSubprofileWeights:
    """Tests for _normalise_subprofile_weights() function."""

    def test_all_zero_weights_equalized(self) -> None:
        """All zero weights should be equalized to 100/N."""
        raw = _make_minimal_profile_dict()
        # Set up 2 subprofiles with zero weights
        raw["seat_profiles"]["N"]["subprofiles"] = [
            {"standard": {}, "weight_percent": 0.0},
            {"standard": {}, "weight_percent": 0.0},
        ]

        _normalise_subprofile_weights(raw)

        weights = [sp["weight_percent"] for sp in raw["seat_profiles"]["N"]["subprofiles"]]
        assert weights == [50.0, 50.0]

    def test_negative_weight_rejected(self) -> None:
        """Negative weights should raise ProfileError."""
        raw = _make_minimal_profile_dict()
        raw["seat_profiles"]["N"]["subprofiles"] = [
            {"standard": {}, "weight_percent": -10.0},
        ]

        with pytest.raises(ProfileError, match="non-negative"):
            _normalise_subprofile_weights(raw)

    def test_sum_near_100_rescaled(self) -> None:
        """Weights summing to ~100 (within ±2) should be rescaled."""
        raw = _make_minimal_profile_dict()
        # Sum = 99, which is within [98, 102]
        raw["seat_profiles"]["N"]["subprofiles"] = [
            {"standard": {}, "weight_percent": 49.0},
            {"standard": {}, "weight_percent": 50.0},
        ]

        _normalise_subprofile_weights(raw)

        weights = [sp["weight_percent"] for sp in raw["seat_profiles"]["N"]["subprofiles"]]
        total = sum(weights)
        assert abs(total - 100.0) < 0.01  # Should sum to exactly 100

    def test_sum_far_from_100_rejected(self) -> None:
        """Weights summing to far from 100 should raise ProfileError."""
        raw = _make_minimal_profile_dict()
        # Sum = 50, which is outside [98, 102]
        raw["seat_profiles"]["N"]["subprofiles"] = [
            {"standard": {}, "weight_percent": 25.0},
            {"standard": {}, "weight_percent": 25.0},
        ]

        with pytest.raises(ProfileError, match="approximately 100"):
            _normalise_subprofile_weights(raw)

    def test_last_gets_slack(self) -> None:
        """Last subprofile should get rounding slack to hit exactly 100."""
        raw = _make_minimal_profile_dict()
        # Weights that don't divide evenly
        raw["seat_profiles"]["N"]["subprofiles"] = [
            {"standard": {}, "weight_percent": 33.33},
            {"standard": {}, "weight_percent": 33.33},
            {"standard": {}, "weight_percent": 33.34},  # Sum = 100.0
        ]

        _normalise_subprofile_weights(raw)

        weights = [sp["weight_percent"] for sp in raw["seat_profiles"]["N"]["subprofiles"]]
        assert sum(weights) == 100.0  # Must be exactly 100

    def test_non_list_subprofiles_rejected(self) -> None:
        """Non-list subprofiles should raise ProfileError."""
        raw = _make_minimal_profile_dict()
        raw["seat_profiles"]["N"]["subprofiles"] = "not a list"

        with pytest.raises(ProfileError, match="must be a list"):
            _normalise_subprofile_weights(raw)


# ---------------------------------------------------------------------------
# Tests for _validate_random_suit_vs_standard
# ---------------------------------------------------------------------------


class TestValidateRandomSuitVsStandard:
    """Tests for _validate_random_suit_vs_standard() function."""

    def test_valid_rs_and_standard_passes(self, make_valid_profile) -> None:
        """Valid RS + standard combination should pass."""
        # Use the fixture which has valid RS constraints
        profile = make_valid_profile()
        # Should not raise
        _validate_random_suit_vs_standard(profile)

    def test_rs_min_exceeds_13_raises(self) -> None:
        """Sum of min_cards > 13 with RS should raise ProfileError."""
        # Create a profile where RS + standard mins exceed 13
        rs = RandomSuitConstraintData(
            required_suits_count=1,
            allowed_suits=["S"],
            suit_ranges=[SuitRange(min_cards=10, max_cards=13)],  # 10 spades min
        )
        # Standard requires 2 of each other suit = 6 cards, plus 10 = 16 > 13
        std = _make_standard(spade_min=0, heart_min=2, diamond_min=2, club_min=2)
        sub = SubProfile(standard=std, random_suit_constraint=rs)
        seat_profile = SeatProfile(seat="N", subprofiles=[sub])

        # Create a minimal HandProfile-like object
        @dataclass
        class MockProfile:
            seat_profiles: Dict[str, SeatProfile]

        profile = MockProfile(seat_profiles={"N": seat_profile})

        with pytest.raises(ProfileError, match="sum of min_cards"):
            _validate_random_suit_vs_standard(profile)

    def test_rs_max_below_13_raises(self) -> None:
        """Sum of max_cards < 13 with RS should raise ProfileError."""
        # Create a profile where RS + standard maxes are below 13
        rs = RandomSuitConstraintData(
            required_suits_count=1,
            allowed_suits=["S"],
            suit_ranges=[SuitRange(min_cards=0, max_cards=3)],  # max 3 spades
        )
        # Standard maxes: 3 each = 9, plus RS max 3 = 12 < 13
        std = StandardSuitConstraints(
            spades=SuitRange(min_cards=0, max_cards=3),
            hearts=SuitRange(min_cards=0, max_cards=3),
            diamonds=SuitRange(min_cards=0, max_cards=3),
            clubs=SuitRange(min_cards=0, max_cards=3),
        )
        sub = SubProfile(standard=std, random_suit_constraint=rs)
        seat_profile = SeatProfile(seat="N", subprofiles=[sub])

        @dataclass
        class MockProfile:
            seat_profiles: Dict[str, SeatProfile]

        profile = MockProfile(seat_profiles={"N": seat_profile})

        with pytest.raises(ProfileError, match="at most"):
            _validate_random_suit_vs_standard(profile)

    def test_skips_if_no_standard(self) -> None:
        """Should skip check if standard constraints are missing."""

        # This tests the legacy case where std is None
        @dataclass
        class MockSubProfile:
            random_suit_constraint: Any = None
            standard: Any = None

        @dataclass
        class MockSeatProfile:
            subprofiles: List[Any]

        @dataclass
        class MockProfile:
            seat_profiles: Dict[str, Any]

        rs = RandomSuitConstraintData(
            required_suits_count=1,
            allowed_suits=["S"],
            suit_ranges=[SuitRange(min_cards=10, max_cards=13)],
        )
        sub = MockSubProfile(random_suit_constraint=rs, standard=None)
        profile = MockProfile(seat_profiles={"N": MockSeatProfile(subprofiles=[sub])})

        # Should not raise because std is None
        _validate_random_suit_vs_standard(profile)


# ---------------------------------------------------------------------------
# Tests for validate_profile (integration)
# ---------------------------------------------------------------------------


class TestValidateProfile:
    """Integration tests for validate_profile() function."""

    def test_full_pipeline_with_valid_dict(self) -> None:
        """Full validation pipeline should work with valid dict input."""
        raw = _make_minimal_profile_dict()
        profile = validate_profile(raw)

        assert isinstance(profile, HandProfile)
        assert profile.profile_name == "TestProfile"
        assert profile.dealer == "N"

    def test_schema_v0_gets_defaults(self) -> None:
        """Schema v0 profiles should get default values applied."""
        raw = _make_minimal_profile_dict()
        raw["schema_version"] = 0
        # Remove fields that should get defaults
        del raw["rotate_deals_by_default"]
        del raw["subprofile_exclusions"]
        del raw["ns_role_mode"]

        profile = validate_profile(raw)

        # Should have defaults applied
        assert profile.rotate_deals_by_default is True
        assert profile.subprofile_exclusions == []
        assert profile.ns_role_mode == "no_driver_no_index"

    def test_accepts_hand_profile_instance(self, make_valid_profile) -> None:
        """Should accept HandProfile instance as input."""
        original = make_valid_profile()
        result = validate_profile(original)

        assert isinstance(result, HandProfile)
        assert result.profile_name == original.profile_name

    def test_validates_partner_contingent_requires_rs(self) -> None:
        """Should reject profiles where PC partner has no RS constraint."""
        raw = _make_minimal_profile_dict()
        # W has partner-contingent on E, but E has no Random-Suit constraint.
        raw["seat_profiles"]["W"]["subprofiles"][0]["partner_contingent_constraint"] = {
            "partner_seat": "E",
            "suit_range": {"min_cards": 0, "max_cards": 13},
        }

        with pytest.raises(ProfileError, match="Random-Suit"):
            validate_profile(raw)
