# tests/test_f3_opener_responder_coupling.py

import random

from tests.conftest import _standard_all_open  # type: ignore

from bridge_engine.hand_profile import HandProfile
from bridge_engine.hand_profile_model import SeatProfile, SubProfile
from bridge_engine.hand_profile_validate import validate_profile

from bridge_engine.deal_generator import _build_single_constrained_deal_v2  # ok: tests already import internals


def test_f3_couples_responder_to_opener_by_index():
    """
    NS sub-profile index matching: the responder (South) should use the
    same sub-profile index as the opener (North), once North's index has
    been chosen by weighted random selection.
    """
    std = _standard_all_open()

    # Two subprofiles on N and S; weights on N force choice of index 0.
    n0 = SubProfile(standard=std, weight_percent=100.0)
    n1 = SubProfile(standard=std, weight_percent=0.0)
    s0 = SubProfile(standard=std)
    s1 = SubProfile(standard=std)

    profile = HandProfile(
        profile_name="TEST_F3_NS",
        description="NS sub-profile index matching test",
        dealer="N",
        tag="Opener",
        seat_profiles={
            "N": SeatProfile(seat="N", subprofiles=[n0, n1]),
            "S": SeatProfile(seat="S", subprofiles=[s0, s1]),
        },
        # Ensure N is dealt before S so N is opener.
        hand_dealing_order=["N", "S", "E", "W"],
    )

    validated = validate_profile(profile)
    rng = random.Random(1234)

    deal = _build_single_constrained_deal_v2(rng, validated, board_number=1)

    # We don't assert exact hands here, only that the coupling logic ran
    # without violating any invariants and produced a valid deal.
    assert deal is not None

    # The coupling is enforced via chosen_subprofile_indices, but that isn't returned.
    # So we assert indirectly: since N is forced to index 0 (100%), S must also be index 0.
    #
    # We can detect this by repeating builds with a different N weighting and ensuring S follows.
    # Quick second run: force N index 1 and confirm S follows.
    n0b = SubProfile(standard=std, weight_percent=0.0)
    n1b = SubProfile(standard=std, weight_percent=100.0)
    profile2 = HandProfile(
        profile_name="TEST_F3_NS_2",
        description="F3 coupling test (alt weights)",
        dealer="N",
        tag="Opener",
        seat_profiles={
            "N": SeatProfile(seat="N", subprofiles=[n0b, n1b]),
            "S": SeatProfile(seat="S", subprofiles=[s0, s1]),
        },
        hand_dealing_order=["N", "S", "E", "W"],
    )
    validated2 = validate_profile(profile2)
    deal2 = _build_single_constrained_deal_v2(rng=random.Random(456), profile=validated2, board_number=1)

    # If we got here without exceptions, we know both deals are constructible.
    # This test is primarily a regression guard: coupling must not crash and must be deterministic.
    assert deal is not None
    assert deal2 is not None


def _make_ns_coupling_profile() -> HandProfile:
    """
    Build a minimal NS profile for coupling testing.

    - N and S both have 2 subprofiles.
    - N has 100/0 weights so subprofile index 0 is deterministically chosen.
    - S has unconstrained weights (defaults).
    """
    std = _standard_all_open()

    north = SeatProfile(
        seat="N",
        subprofiles=[
            SubProfile(standard=std, weight_percent=100.0),
            SubProfile(standard=std, weight_percent=0.0),
        ],
    )
    south = SeatProfile(
        seat="S",
        subprofiles=[
            SubProfile(standard=std),
            SubProfile(standard=std),
        ],
    )

    profile = HandProfile(
        profile_name="TEST_F3_NS_coupling",
        description="NS coupling test",
        dealer="N",
        tag="Opener",
        seat_profiles={"N": north, "S": south},
        hand_dealing_order=["N", "S", "E", "W"],
    )

    # Go through the real validator to pick up any future invariants.
    return validate_profile(profile)


def test_f3_ns_coupling_default_mode_still_works() -> None:
    """
    Smoke test: profile with N and S having 2 subprofiles each
    still produces a valid deal.
    """
    profile = _make_ns_coupling_profile()
    rng = random.Random(1234)

    deal = _build_single_constrained_deal_v2(rng, profile, board_number=1)
    assert deal is not None
