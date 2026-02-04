# test_deal_generator_unviable.py
"""
Tests for P1.3: Early termination when profile is unviable ("too hard" rule).
"""

from __future__ import annotations

import pytest
import random

from bridge_engine.deal_generator import (
    DealGenerationError,
    _build_single_constrained_deal,
    MIN_ATTEMPTS_FOR_UNVIABLE_CHECK,
    MAX_BOARD_ATTEMPTS,
)

from bridge_engine.hand_profile import (
    HandProfile,
    SeatProfile,
    SubProfile,
    StandardSuitConstraints,
    SuitRange,
)


def _impossible_profile() -> HandProfile:
    """
    Create a profile with impossible constraints.

    North requires exactly 13 spades AND at least 1 heart, which is
    impossible since a hand has only 13 cards total. This should
    trigger early termination.
    """
    # Impossible: require 13 spades AND 1+ hearts (total > 13 cards)
    spades_13 = SuitRange(min_cards=13, max_cards=13, min_hcp=0, max_hcp=37)
    hearts_1_plus = SuitRange(min_cards=1, max_cards=13, min_hcp=0, max_hcp=37)
    wide_suit = SuitRange(min_cards=0, max_cards=13, min_hcp=0, max_hcp=37)

    north_std = StandardSuitConstraints(
        spades=spades_13,        # 13 spades required
        hearts=hearts_1_plus,    # Plus 1+ hearts = impossible!
        diamonds=wide_suit,
        clubs=wide_suit,
        total_min_hcp=0,
        total_max_hcp=37,
    )

    wide_std = StandardSuitConstraints(
        spades=wide_suit,
        hearts=wide_suit,
        diamonds=wide_suit,
        clubs=wide_suit,
        total_min_hcp=0,
        total_max_hcp=37,
    )

    north_profile = SeatProfile(seat="N", subprofiles=[SubProfile(north_std)])
    east_profile = SeatProfile(seat="E", subprofiles=[SubProfile(wide_std)])
    south_profile = SeatProfile(seat="S", subprofiles=[SubProfile(wide_std)])
    west_profile = SeatProfile(seat="W", subprofiles=[SubProfile(wide_std)])

    return HandProfile(
        profile_name="Impossible_Test_Profile",
        description="Profile with impossible constraints for testing early termination",
        dealer="N",
        hand_dealing_order=["N", "E", "S", "W"],
        tag="Opener",
        author="Test",
        version="0.1",
        seat_profiles={
            "N": north_profile,
            "E": east_profile,
            "S": south_profile,
            "W": west_profile,
        },
    )


def test_impossible_profile_terminates_early():
    """
    P1.3: Impossible profiles should terminate early with clear error message.

    The profile requires 14 spades for North (impossible - max 13 cards in hand).
    After MIN_ATTEMPTS_FOR_UNVIABLE_CHECK attempts with >90% failure rate,
    the generator should raise DealGenerationError mentioning "unviable".
    """
    profile = _impossible_profile()
    rng = random.Random(42)

    with pytest.raises(DealGenerationError) as exc_info:
        _build_single_constrained_deal(
            rng=rng,
            profile=profile,
            board_number=1,
        )

    error_msg = str(exc_info.value)

    # Verify error message mentions "unviable"
    assert "unviable" in error_msg.lower(), f"Error should mention 'unviable': {error_msg}"

    # Verify it mentions North (the problematic seat)
    assert "N" in error_msg, f"Error should mention seat 'N': {error_msg}"

    # Verify it terminated before MAX_BOARD_ATTEMPTS
    # The error message format includes attempt count
    assert str(MAX_BOARD_ATTEMPTS) not in error_msg, (
        f"Should have terminated early, not at MAX_BOARD_ATTEMPTS: {error_msg}"
    )


def test_impossible_profile_terminates_after_min_attempts():
    """
    P1.3: Early termination should not happen before MIN_ATTEMPTS_FOR_UNVIABLE_CHECK.

    This verifies the safeguard that prevents premature termination before
    we have enough data for reliable viability classification.
    """
    profile = _impossible_profile()
    rng = random.Random(42)

    with pytest.raises(DealGenerationError) as exc_info:
        _build_single_constrained_deal(
            rng=rng,
            profile=profile,
            board_number=1,
        )

    error_msg = str(exc_info.value)

    # Extract attempt count from error message
    # Format: "... after X attempts ..."
    import re
    match = re.search(r"after (\d+) attempts", error_msg)
    assert match, f"Could not extract attempt count from: {error_msg}"

    attempts = int(match.group(1))

    # Verify we waited at least MIN_ATTEMPTS_FOR_UNVIABLE_CHECK
    assert attempts >= MIN_ATTEMPTS_FOR_UNVIABLE_CHECK, (
        f"Should have waited at least {MIN_ATTEMPTS_FOR_UNVIABLE_CHECK} attempts, "
        f"but terminated after {attempts}"
    )

    # Verify we didn't grind to MAX_BOARD_ATTEMPTS
    assert attempts < MAX_BOARD_ATTEMPTS, (
        f"Should have terminated early, not at {MAX_BOARD_ATTEMPTS}"
    )
