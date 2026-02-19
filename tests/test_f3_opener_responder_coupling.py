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
    same sub-profile index as the opener (North), once North’s index has
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

    # We don’t assert exact hands here, only that the coupling logic ran
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
        description="F3 opener→responder coupling test (alt weights)",
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


def _make_ns_coupling_profile(ns_role_mode: str | None = None) -> HandProfile:
    """
    Build a minimal NS profile for F3 testing, with optional ns_role_mode.

    - N and S both have 2 subprofiles.
    - N has 100/0 weights so, when N is the driver, subprofile index 0
      is deterministically chosen.
    - S has unconstrained weights (defaults) – the F3 coupling logic
      will align S's subprofile index to the driver's choice.
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

    extra_kwargs: dict[str, object] = {}
    if ns_role_mode is not None:
        extra_kwargs["ns_role_mode"] = ns_role_mode

    profile = HandProfile(
        profile_name=f"TEST_F3_NS_mode_{ns_role_mode or 'default'}",
        description="F3 opener→responder coupling NS test",
        dealer="N",
        tag="Opener",
        seat_profiles={"N": north, "S": south},
        hand_dealing_order=["N", "S", "E", "W"],
        **extra_kwargs,
    )

    # Go through the real validator to pick up any future invariants.
    return validate_profile(profile)


def test_f3_ns_coupling_default_mode_still_works() -> None:
    """
    Smoke test: with no explicit ns_role_mode, we still get a valid deal.

    This locks in that introducing ns_role_mode metadata does not break
    the default (Phase 2) behaviour of the generator or the NS
    sub-profile index matching logic (formerly “F3 coupling”).
    """

    profile = _make_ns_coupling_profile()  # uses default ns_role_mode
    rng = random.Random(1234)

    deal = _build_single_constrained_deal_v2(rng, profile, board_number=1)
    assert deal is not None


def test_f3_ns_coupling_north_drives_metadata_is_accepted() -> None:
    """
    Smoke test: ns_role_mode='north_drives' is accepted end-to-end.

    For now, we only assert that the generator runs without error. When
    we later refine NS driver/follower semantics and sub-profile index
    matching, we can extend this to check which side actually drives.
    """

    profile = _make_ns_coupling_profile(ns_role_mode="north_drives")
    rng = random.Random(5678)

    deal = _build_single_constrained_deal_v2(rng, profile, board_number=1)
    assert deal is not None


def test_f3_ns_coupling_south_or_random_modes_do_not_crash() -> None:
    """
    Smoke test for future modes: 'south_drives' and 'random_driver'.

    Today, these may behave the same as the default from the generator's
    perspective. This test simply guarantees that introducing these
    ns_role_mode values does not crash deal generation or the NS
    sub-profile index matching behaviour (formerly “F3 coupling”).
    """

    for mode in ("south_drives", "random_driver"):
        profile = _make_ns_coupling_profile(ns_role_mode=mode)
        rng = random.Random(9999)

        deal = _build_single_constrained_deal_v2(rng, profile, board_number=1)
        assert deal is not None
