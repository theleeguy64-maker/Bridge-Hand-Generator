from __future__ import annotations

from dataclasses import replace

import pytest

from bridge_engine.seat_viability import validate_profile_viability_light

from bridge_engine.hand_profile import (
    SuitRange,
    StandardSuitConstraints,
    validate_profile,
    ProfileError,
)


def test_validate_profile_viability_light_accepts_simple_valid_profile(make_valid_profile) -> None:
    """
    Light viability sanity: a minimal valid profile should validate.
    """
    profile = make_valid_profile()
    validate_profile_viability_light(profile)  # should not raise


def test_validate_profile_viability_light_rejects_impossible_standard_for_seat(make_valid_profile) -> None:
    """
    Light viability sanity: reject a profile where a seat has impossible
    standard constraints (sum of suit minimums exceeds 13 cards).
    """
    profile = make_valid_profile()

    # Make North's first subprofile impossible: 4+4+4+4 = 16 minimum cards.
    impossible_range = SuitRange(min_cards=4, max_cards=13)
    impossible_standard = StandardSuitConstraints(
        spades=impossible_range,
        hearts=impossible_range,
        diamonds=impossible_range,
        clubs=impossible_range,
    )

    north = profile.seat_profiles["N"]
    old_sub = north.subprofiles[0]
    new_sub = replace(old_sub, standard=impossible_standard)
    new_north = replace(north, subprofiles=[new_sub] + list(north.subprofiles[1:]))

    new_seat_profiles = dict(profile.seat_profiles)
    new_seat_profiles["N"] = new_north
    new_profile = replace(profile, seat_profiles=new_seat_profiles)

    with pytest.raises(ProfileError):
        validate_profile_viability_light(new_profile)
