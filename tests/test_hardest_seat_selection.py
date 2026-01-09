from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

import pytest

from bridge_engine.deal_generator import (
    HardestSeatConfig,
    _choose_hardest_seat_for_board,
    _seat_has_nonstandard_constraints,
)

Seat = str


# ---------------------------------------------------------------------------
# Dummy model types for exercising the hardest-seat helpers
# ---------------------------------------------------------------------------


@dataclass
class DummySubProfile:
    random_suit_constraint: Any = None
    partner_contingent_constraint: Any = None
    opponents_contingent_suit_constraint: Any = None


@dataclass
class DummySeatProfile:
    subprofiles: List[DummySubProfile] = field(default_factory=list)


@dataclass
class DummyProfile:
    seat_profiles: Dict[Seat, DummySeatProfile] = field(default_factory=dict)
    is_invariants_safety_profile: bool = False


# Small factory helpers ------------------------------------------------------


def _profile_with_standard_constraints_only() -> DummyProfile:
    """All seats present but no non-standard constraints."""

    def std_seat() -> DummySeatProfile:
        return DummySeatProfile(subprofiles=[DummySubProfile()])

    return DummyProfile(
        seat_profiles={
            "N": std_seat(),
            "E": std_seat(),
            "S": std_seat(),
            "W": std_seat(),
        },
        is_invariants_safety_profile=False,
    )


def _profile_with_random_suit_on_north_only() -> DummyProfile:
    """North has Random Suit; others are standard-only."""

    north = DummySeatProfile(subprofiles=[DummySubProfile(random_suit_constraint=object())])

    def std_seat() -> DummySeatProfile:
        return DummySeatProfile(subprofiles=[DummySubProfile()])

    return DummyProfile(
        seat_profiles={
            "N": north,
            "E": std_seat(),
            "S": std_seat(),
            "W": std_seat(),
        },
        is_invariants_safety_profile=False,
    )


def _invariants_safety_profile() -> DummyProfile:
    """Profile that would use the invariants fast-path in deal_generator."""
    # No need for real seats here; the flag alone is enough.
    return DummyProfile(seat_profiles={}, is_invariants_safety_profile=True)


# ---------------------------------------------------------------------------
# Tests for _seat_has_nonstandard_constraints
# ---------------------------------------------------------------------------


def test_seat_has_nonstandard_constraints_detection() -> None:
    profile = _profile_with_random_suit_on_north_only()

    assert _seat_has_nonstandard_constraints(profile, "N") is True
    # All others should be standard-only.
    for seat in ("E", "S", "W"):
        assert _seat_has_nonstandard_constraints(profile, seat) is False


# ---------------------------------------------------------------------------
# Tests for _choose_hardest_seat_for_board
# ---------------------------------------------------------------------------


def test_hardest_seat_none_before_min_attempts() -> None:
    profile = _profile_with_standard_constraints_only()
    fail_counts = {"N": 10, "E": 5}
    seen_counts = {"N": 10, "E": 5}

    cfg = HardestSeatConfig(
        min_attempts_before_help=50,
        min_fail_count_for_help=3,
        min_fail_rate_for_help=0.7,
    )

    seat = _choose_hardest_seat_for_board(
        profile=profile,
        seat_fail_counts=fail_counts,
        seat_seen_counts=seen_counts,
        dealing_order=["N", "E", "S", "W"],
        attempt_number=10,
        cfg=cfg,
    )
    assert seat is None


def test_hardest_seat_chooses_highest_fail_rate() -> None:
    profile = _profile_with_standard_constraints_only()
    # N: 8/10 = 0.8, E: 3/10 = 0.3
    fail_counts = {"N": 8, "E": 3}
    seen_counts = {"N": 10, "E": 10}

    cfg = HardestSeatConfig(
        min_attempts_before_help=1,
        min_fail_count_for_help=1,
        min_fail_rate_for_help=0.5,
    )

    seat = _choose_hardest_seat_for_board(
        profile=profile,
        seat_fail_counts=fail_counts,
        seat_seen_counts=seen_counts,
        dealing_order=["N", "E", "S", "W"],
        attempt_number=5,
        cfg=cfg,
    )
    assert seat == "N"


def test_hardest_seat_respects_min_fail_count() -> None:
    profile = _profile_with_standard_constraints_only()
    # N below fail-count threshold
    fail_counts = {"N": 2, "E": 10}
    seen_counts = {"N": 2, "E": 10}

    cfg = HardestSeatConfig(
        min_attempts_before_help=1,
        min_fail_count_for_help=3,
        min_fail_rate_for_help=0.1,
    )

    seat = _choose_hardest_seat_for_board(
        profile=profile,
        seat_fail_counts=fail_counts,
        seat_seen_counts=seen_counts,
        dealing_order=["N", "E", "S", "W"],
        attempt_number=50,
        cfg=cfg,
    )
    assert seat == "E"


def test_hardest_seat_respects_min_fail_rate() -> None:
    profile = _profile_with_standard_constraints_only()
    # N: 5/20 = 0.25, E: 5/5 = 1.0
    fail_counts = {"N": 5, "E": 5}
    seen_counts = {"N": 20, "E": 5}

    cfg = HardestSeatConfig(
        min_attempts_before_help=1,
        min_fail_count_for_help=1,
        min_fail_rate_for_help=0.8,
    )

    seat = _choose_hardest_seat_for_board(
        profile=profile,
        seat_fail_counts=fail_counts,
        seat_seen_counts=seen_counts,
        dealing_order=["N", "E", "S", "W"],
        attempt_number=50,
        cfg=cfg,
    )
    assert seat == "E"


def test_hardest_seat_prefers_nonstandard_when_tied() -> None:
    profile = _profile_with_random_suit_on_north_only()
    # Same fail stats for N and E; N has non-standard constraints.
    fail_counts = {"N": 7, "E": 7}
    seen_counts = {"N": 10, "E": 10}

    cfg = HardestSeatConfig(
        min_attempts_before_help=1,
        min_fail_count_for_help=1,
        min_fail_rate_for_help=0.5,
        prefer_nonstandard_seats=True,
    )

    seat = _choose_hardest_seat_for_board(
        profile=profile,
        seat_fail_counts=fail_counts,
        seat_seen_counts=seen_counts,
        dealing_order=["N", "E", "S", "W"],
        attempt_number=50,
        cfg=cfg,
    )
    assert seat == "N"


def test_hardest_seat_tie_breaks_by_dealing_order() -> None:
    profile = _profile_with_standard_constraints_only()
    # Equal stats; earliest in dealing_order should win when prefer_nonstandard=False.
    fail_counts = {"N": 5, "E": 5}
    seen_counts = {"N": 10, "E": 10}

    cfg = HardestSeatConfig(
        min_attempts_before_help=1,
        min_fail_count_for_help=1,
        min_fail_rate_for_help=0.1,
        prefer_nonstandard_seats=False,
    )

    seat = _choose_hardest_seat_for_board(
        profile=profile,
        seat_fail_counts=fail_counts,
        seat_seen_counts=seen_counts,
        dealing_order=["E", "N", "S", "W"],
        attempt_number=50,
        cfg=cfg,
    )
    assert seat == "E"


def test_hardest_seat_none_for_invariants_safety_profile() -> None:
    profile = _invariants_safety_profile()

    cfg = HardestSeatConfig(
        min_attempts_before_help=1,
        min_fail_count_for_help=1,
        min_fail_rate_for_help=0.0,
    )

    seat = _choose_hardest_seat_for_board(
        profile=profile,
        seat_fail_counts={"N": 100},
        seat_seen_counts={"N": 100},
        dealing_order=["N", "E", "S", "W"],
        attempt_number=200,
        cfg=cfg,
    )
    assert seat is None
   