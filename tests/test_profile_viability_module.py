"""
Tests for bridge_engine/profile_viability.py

Tests the actual profile_viability module (not the toy model in
test_profile_viability_extended.py). These tests verify the edge cases
around NS index-coupling and the ns_role_mode field.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pytest

from bridge_engine.hand_profile_model import ProfileError

from bridge_engine.profile_viability import (
    _ns_pair_jointly_viable,
    validate_profile_viability,
)
from bridge_engine.hand_profile_model import (
    SubProfile,
    SeatProfile,
    SuitRange,
    StandardSuitConstraints,
)


# ---------------------------------------------------------------------------
# Test fixtures - minimal objects for testing
# ---------------------------------------------------------------------------

def _make_standard(spade_min=0, spade_max=13, heart_min=0, heart_max=13,
                   diamond_min=0, diamond_max=13, club_min=0, club_max=13,
                   min_hcp=0, max_hcp=37) -> StandardSuitConstraints:
    """Helper to create StandardSuitConstraints."""
    return StandardSuitConstraints(
        spades=SuitRange(min_cards=spade_min, max_cards=spade_max),
        hearts=SuitRange(min_cards=heart_min, max_cards=heart_max),
        diamonds=SuitRange(min_cards=diamond_min, max_cards=diamond_max),
        clubs=SuitRange(min_cards=club_min, max_cards=club_max),
        total_min_hcp=min_hcp,
        total_max_hcp=max_hcp,
    )


def _make_subprofile(spade_min=0, heart_min=0, diamond_min=0, club_min=0,
                     min_hcp=0, max_hcp=37) -> SubProfile:
    """Helper to create SubProfile with specified suit minima."""
    return SubProfile(
        standard=_make_standard(
            spade_min=spade_min, heart_min=heart_min,
            diamond_min=diamond_min, club_min=club_min,
            min_hcp=min_hcp, max_hcp=max_hcp,
        ),
    )


@dataclass
class MockSubProfileForNsPair:
    """
    Minimal mock subprofile for testing _ns_pair_jointly_viable only.

    The function accesses min_suit_counts via getattr() with default.
    """
    min_suit_counts: Dict[str, int] = field(default_factory=dict)


@dataclass
class MockHandProfile:
    """
    Minimal mock hand profile for testing validate_profile_viability.

    The function accesses:
      - seat_profiles (dict of seat -> SeatProfile)
      - ns_role_mode (str) — coupling enabled when not "no_driver_no_index"
    """
    seat_profiles: Dict[str, SeatProfile] = field(default_factory=dict)
    # "north_drives" enables coupling; "no_driver_no_index" disables it.
    ns_role_mode: str = "north_drives"


# ---------------------------------------------------------------------------
# Tests for _ns_pair_jointly_viable
# ---------------------------------------------------------------------------

def test_ns_pair_jointly_viable_passes_when_ok() -> None:
    """Valid NS pair with combined suit minima <= 13 should return True."""
    n_sub = MockSubProfileForNsPair(min_suit_counts={"S": 5, "H": 3, "D": 2, "C": 1})
    s_sub = MockSubProfileForNsPair(min_suit_counts={"S": 3, "H": 5, "D": 2, "C": 2})

    # S: 5+3=8 <= 13, H: 3+5=8 <= 13, D: 2+2=4 <= 13, C: 1+2=3 <= 13
    assert _ns_pair_jointly_viable(n_sub, s_sub) is True


def test_ns_pair_jointly_viable_suit_min_exceeds_13() -> None:
    """Combined suit minima > 13 for any suit should return False."""
    n_sub = MockSubProfileForNsPair(min_suit_counts={"S": 10, "H": 0, "D": 0, "C": 0})
    s_sub = MockSubProfileForNsPair(min_suit_counts={"S": 4, "H": 0, "D": 0, "C": 0})

    # S: 10+4=14 > 13, should fail
    assert _ns_pair_jointly_viable(n_sub, s_sub) is False


def test_ns_pair_jointly_viable_exactly_13() -> None:
    """Combined suit minima exactly 13 should return True (edge case)."""
    n_sub = MockSubProfileForNsPair(min_suit_counts={"S": 7, "H": 0, "D": 0, "C": 0})
    s_sub = MockSubProfileForNsPair(min_suit_counts={"S": 6, "H": 0, "D": 0, "C": 0})

    # S: 7+6=13 <= 13, should pass
    assert _ns_pair_jointly_viable(n_sub, s_sub) is True


def test_ns_pair_jointly_viable_missing_suit_counts() -> None:
    """Missing suit counts should default to 0 and pass."""
    n_sub = MockSubProfileForNsPair(min_suit_counts={})  # No minima specified
    s_sub = MockSubProfileForNsPair(min_suit_counts={})

    # All suits default to 0, should pass
    assert _ns_pair_jointly_viable(n_sub, s_sub) is True


# ---------------------------------------------------------------------------
# Tests for validate_profile_viability
# ---------------------------------------------------------------------------

def test_validate_profile_viability_respects_coupling_disabled() -> None:
    """
    When ns_role_mode="no_driver_no_index", NS coupling checks should be skipped.

    This means even impossible NS pairs won't cause validation to fail
    (as long as each subprofile is individually viable and the cross-seat
    check passes).
    """
    # Create subprofiles that would fail coupling check if enabled at index 0.
    # N[0] wants 7 spades, S[0] wants 7 spades → combined 14 > 13 (coupling fails).
    # But N[1] wants 0 spades, S[1] wants 0 spades → best-case for cross-seat is 0.
    # Cross-seat best case: N sub with 7 spades vs S best-case min 0 → 7+0=7 ≤ 13 → alive.
    n_sub_tight = _make_subprofile(spade_min=7)
    n_sub_loose = _make_subprofile(spade_min=0)
    s_sub_tight = _make_subprofile(spade_min=7)
    s_sub_loose = _make_subprofile(spade_min=0)

    profile = MockHandProfile(
        seat_profiles={
            "N": SeatProfile(seat="N", subprofiles=[n_sub_tight, n_sub_loose]),
            "S": SeatProfile(seat="S", subprofiles=[s_sub_tight, s_sub_loose]),
        },
        ns_role_mode="no_driver_no_index",  # Disable coupling checks
    )

    # Should NOT raise: coupling is disabled, and cross-seat check passes
    # because best-case min for each seat is 0 spades.
    validate_profile_viability(profile)


def test_validate_profile_viability_respects_coupling_enabled() -> None:
    """
    When ns_role_mode enables coupling (e.g. "north_drives"), NS coupling
    checks run. An impossible NS pair at any index should raise ValueError.
    """
    # Index 0: viable pair (low spade requirements)
    viable_n = _make_subprofile(spade_min=3, heart_min=3, diamond_min=3, club_min=3)
    viable_s = _make_subprofile(spade_min=3, heart_min=3, diamond_min=3, club_min=3)

    # Index 1: impossible pair (combined spades = 14 > 13)
    impossible_n = _make_subprofile(spade_min=7)
    impossible_s = _make_subprofile(spade_min=7)

    profile = MockHandProfile(
        seat_profiles={
            "N": SeatProfile(seat="N", subprofiles=[viable_n, impossible_n]),
            "S": SeatProfile(seat="S", subprofiles=[viable_s, impossible_s]),
        },
        ns_role_mode="north_drives",  # Enable coupling checks
    )

    # Should raise because index 1 is not jointly viable
    with pytest.raises(ProfileError, match="not jointly viable"):
        validate_profile_viability(profile)


def test_validate_profile_viability_unequal_subprofile_lengths() -> None:
    """
    Unequal N/S subprofile counts should skip NS coupling checks.
    """
    # Would fail coupling if checked, but lengths are unequal.
    # Include a loose sub so cross-seat best-case is feasible (0+0=0 ≤ 13).
    n_sub_tight = _make_subprofile(spade_min=7)
    n_sub_loose = _make_subprofile(spade_min=0)
    s_sub_tight = _make_subprofile(spade_min=7)
    s_sub_loose = _make_subprofile(spade_min=0)

    profile = MockHandProfile(
        seat_profiles={
            "N": SeatProfile(seat="N", subprofiles=[n_sub_tight, n_sub_loose]),
            "S": SeatProfile(seat="S", subprofiles=[s_sub_tight, s_sub_loose, s_sub_loose]),  # Different length
        },
        ns_role_mode="north_drives",
    )

    # Should NOT raise: lengths are unequal (coupling skipped),
    # and cross-seat passes because best-case min is 0.
    validate_profile_viability(profile)


def test_validate_profile_viability_single_subprofile() -> None:
    """
    Single subprofile per seat should skip NS coupling checks.

    Use spade_min=6 on each so cross-seat check passes (6+6=12 ≤ 13).
    With only 1 sub per seat, coupling is skipped (requires >1 sub per seat).
    """
    n_sub = _make_subprofile(spade_min=6)
    s_sub = _make_subprofile(spade_min=6)

    profile = MockHandProfile(
        seat_profiles={
            "N": SeatProfile(seat="N", subprofiles=[n_sub]),
            "S": SeatProfile(seat="S", subprofiles=[s_sub]),
        },
        ns_role_mode="north_drives",
    )

    # Should NOT raise: single subprofile per seat skips coupling,
    # and cross-seat passes (6+6=12 ≤ 13 per suit).
    validate_profile_viability(profile)


def test_validate_profile_viability_no_viable_pair_raises() -> None:
    """
    If no NS index has both sides viable, should raise ValueError.

    This happens when N[i] is viable but S[i] is not (or vice versa)
    for all indices.
    """
    # N[0] is viable, S[0] is not viable (suit minima > 13)
    # N[1] is not viable, S[1] is viable
    viable_sub = _make_subprofile(spade_min=3, heart_min=3, diamond_min=3, club_min=3)
    # Impossible: sum of minima = 4+4+4+4 = 16 > 13
    impossible_sub = _make_subprofile(spade_min=4, heart_min=4, diamond_min=4, club_min=4)

    profile = MockHandProfile(
        seat_profiles={
            "N": SeatProfile(seat="N", subprofiles=[viable_sub, impossible_sub]),
            "S": SeatProfile(seat="S", subprofiles=[impossible_sub, viable_sub]),
        },
        ns_role_mode="north_drives",
    )

    # Index 0: N viable, S not viable (suit mins > 13)
    # Index 1: N not viable, S viable
    # No index where both are viable
    with pytest.raises(ProfileError, match="No NS index-coupled subprofile pair is jointly viable"):
        validate_profile_viability(profile)


def test_validate_profile_viability_no_n_or_s_seat() -> None:
    """
    Profiles without both N and S seats should skip coupling checks.
    """
    n_sub = _make_subprofile(spade_min=7)

    # Only N, no S
    profile = MockHandProfile(
        seat_profiles={
            "N": SeatProfile(seat="N", subprofiles=[n_sub, n_sub]),
        },
        ns_role_mode="north_drives",
    )

    # Should NOT raise because S is missing
    validate_profile_viability(profile)
