# tests/test_ew_index_coupling.py

import random
from typing import Dict, List

from bridge_engine import deal_generator


class DummySubprofile:
    """Minimal stand-in for a subprofile.

    We don't care about real constraints here; we just need something
    that can live in seat_profile.subprofiles.
    """

    def __init__(self, weight_percent: float | None = None, nonstandard: bool = False):
        if weight_percent is not None:
            self.weight_percent = weight_percent

        # Optional non-standard flags; not used in this test but kept
        # for symmetry with other dummy helpers if we extend later.
        if nonstandard:
            self.random_suit_constraint = object()


class DummySeatProfile:
    """Minimal stand-in for SeatProfile used by deal_generator."""

    def __init__(self, subprofiles: List[DummySubprofile]):
        self.subprofiles = list(subprofiles)


class DummyProfile:
    """Profile with EW both multi-subprofile so EW coupling should kick in."""

    def __init__(self) -> None:
        self.profile_name = "Dummy_EW_coupling_profile"
        self.dealer = "N"
        # Make E appear before W so E is the EW driver.
        self.hand_dealing_order = ["N", "E", "S", "W"]

        # N/S unconstrained (no subprofiles); E/W each have 2 subprofiles.
        self.seat_profiles: Dict[str, DummySeatProfile] = {
            "N": DummySeatProfile([]),
            "E": DummySeatProfile(
                [
                    DummySubprofile(weight_percent=80.0),
                    DummySubprofile(weight_percent=20.0),
                ]
            ),
            "S": DummySeatProfile([]),
            "W": DummySeatProfile(
                [
                    DummySubprofile(weight_percent=20.0),
                    DummySubprofile(weight_percent=80.0),
                ]
            ),
        }

        # Disable NS coupling entirely; we only care about EW here.
        self.ns_index_coupling_enabled = False

    # Called by deal_generator when NS coupling is considered.
    def ns_driver_seat(self, rng: random.Random) -> str | None:  # pragma: no cover - trivial
        return None


def test_ew_index_coupling_driver_and_follower_share_index(monkeypatch) -> None:
    """
    EW index coupling: when both E and W have multiple subprofiles with equal
    length, _build_single_constrained_deal must choose a *single* index for
    the EW "driver" seat and force the follower to use the same index.

    This test doesn't care about the actual weight distribution, only that
    E and W end up with the same chosen_subprofile_index_1based in _match_seat.
    """
    profile = DummyProfile()

    # Make isinstance(..., SeatProfile) accept our dummy seat profiles.
    monkeypatch.setattr(deal_generator, "SeatProfile", DummySeatProfile)

    captured_indices: Dict[str, int] = {}

    # Intercept _match_seat to record the 1-based index used per seat.
    def fake_match_seat(
        *,
        profile,
        seat,
        hand,
        seat_profile,
        chosen_subprofile,
        chosen_subprofile_index_1based,
        random_suit_choices,
        rng,
    ):
        captured_indices[seat] = chosen_subprofile_index_1based
        # Always "match" so the first attempt succeeds and we don't trigger
        # any of the fallback / debug-hook behaviour.
        return True, None, None

    monkeypatch.setattr(deal_generator, "_match_seat", fake_match_seat)

    rng = random.Random(1234)

    # Act: build a single constrained deal. If EW coupling is working,
    # E and W should see the same chosen_subprofile_index_1based.
    _ = deal_generator._build_single_constrained_deal(  # type: ignore[attr-defined]
        rng=rng,
        profile=profile,
        board_number=1,
    )

    # Sanity: both E and W were actually matched.
    assert "E" in captured_indices
    assert "W" in captured_indices

    # The core property: EW index-coupled seats share the same index.
    assert captured_indices["E"] == captured_indices["W"]
    # And the index is 1-based and within the expected range [1, 2].
    assert captured_indices["E"] in (1, 2)