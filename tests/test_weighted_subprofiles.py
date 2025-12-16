# tests/test_weighted_subprofiles.py

from __future__ import annotations

import random

import pytest

from bridge_engine.hand_profile import (
    HandProfile,
    SeatProfile,
    SubProfile,
    StandardSuitConstraints,
    SuitRange,
    validate_profile,
    ProfileError,
)
from bridge_engine.deal_generator import _weighted_choice_index


def _simple_std() -> StandardSuitConstraints:
    """Helper: a fully-open StandardSuitConstraints."""
    sr = SuitRange()
    return StandardSuitConstraints(
        spades=sr,
        hearts=sr,
        diamonds=sr,
        clubs=sr,
        total_min_hcp=0,
        total_max_hcp=37,
    )


def test_legacy_profile_equalises_weights():
    """
    Legacy profile with no weight_percent values should get equal weights
    per seat after validate_profile.
    """
    std = _simple_std()
    sub_a = SubProfile(standard=std)  # weight_percent defaults to 0.0
    sub_b = SubProfile(standard=std)

    profile = HandProfile(
        profile_name="Legacy",
        description="",
        dealer="N",
        hand_dealing_order=["N", "E", "S", "W"],
        tag="Opener",
        seat_profiles={
            "N": SeatProfile(seat="N", subprofiles=[sub_a, sub_b]),
        },
    )

    validated = validate_profile(profile)
    w0 = validated.seat_profiles["N"].subprofiles[0].weight_percent
    w1 = validated.seat_profiles["N"].subprofiles[1].weight_percent

    # Should be roughly 50/50 and sum to 100.0
    assert pytest.approx(w0 + w1, rel=0, abs=1e-6) == 100.0
    assert pytest.approx(w0, rel=0, abs=1.0) == 50.0
    assert pytest.approx(w1, rel=0, abs=1.0) == 50.0


def test_negative_weight_rejected():
    std = _simple_std()
    sub = SubProfile(standard=std, weight_percent=-5.0)
    profile = HandProfile(
        profile_name="Bad",
        description="",
        dealer="N",
        hand_dealing_order=["N", "E", "S", "W"],
        tag="Opener",
        seat_profiles={
            "N": SeatProfile(seat="N", subprofiles=[sub]),
        },
    )
    with pytest.raises(ProfileError):
        validate_profile(profile)


def test_sum_far_from_100_rejected():
    std = _simple_std()
    sub_a = SubProfile(standard=std, weight_percent=10.0)
    sub_b = SubProfile(standard=std, weight_percent=10.0)
    profile = HandProfile(
        profile_name="BadSum",
        description="",
        dealer="N",
        hand_dealing_order=["N", "E", "S", "W"],
        tag="Opener",
        seat_profiles={
            "N": SeatProfile(seat="N", subprofiles=[sub_a, sub_b]),
        },
    )
    with pytest.raises(ProfileError):
        validate_profile(profile)


def test_sum_near_100_is_normalised():
    """
    If total is within ±2 of 100, validate_profile should normalise.
    """
    std = _simple_std()
    sub_a = SubProfile(standard=std, weight_percent=40.0)
    sub_b = SubProfile(standard=std, weight_percent=40.0)
    sub_c = SubProfile(standard=std, weight_percent=20.0)  # total = 100.0
    # Now tweak slightly: 39.0, 39.0, 20.0 => total = 98.0, within 2%
    sub_a = SubProfile(standard=std, weight_percent=39.0)
    sub_b = SubProfile(standard=std, weight_percent=39.0)
    sub_c = SubProfile(standard=std, weight_percent=20.0)

    profile = HandProfile(
        profile_name="NearHundred",
        description="",
        dealer="N",
        hand_dealing_order=["N", "E", "S", "W"],
        tag="Opener",
        seat_profiles={
            "N": SeatProfile(seat="N", subprofiles=[sub_a, sub_b, sub_c]),
        },
    )

    validated = validate_profile(profile)
    weights = [
        sp.weight_percent for sp in validated.seat_profiles["N"].subprofiles
    ]
    assert pytest.approx(sum(weights), rel=0, abs=1e-6) == 100.0


def test_weighted_choice_index_skewed_distribution():
    """
    _weighted_choice_index should favour larger weights with a fixed seed.
    """
    rng = random.Random(12345)
    weights = [10.0, 90.0]
    counts = [0, 0]
    for _ in range(1000):
        idx = _weighted_choice_index(rng, weights)
        counts[idx] += 1

    # Second index should be much more frequent
    assert counts[1] > counts[0] * 3