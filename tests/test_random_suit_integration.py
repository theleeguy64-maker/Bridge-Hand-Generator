# tests/test_random_suit_integration.py

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import random
import pytest

from bridge_engine import deal_generator


Seat = str  # reuse the alias style from the engine if exported, else str is fine.


# --- Dummy types to drive _build_single_constrained_deal ----------------------


@dataclass
class DummySubProfile:
    random_suit_constraint: Optional[object] = None
    partner_contingent_constraint: Optional[object] = None
    opponents_contingent_suit_constraint: Optional[object] = None
    weight_percent: Optional[float] = None  # so _weights_for_seat_profile is happy


@dataclass
class DummySeatProfile:
    subprofiles: List[DummySubProfile]


@dataclass
class DummyProfile:
    seat_profiles: Dict[Seat, DummySeatProfile]
    hand_dealing_order: List[Seat]
    dealer: Seat = "N"
    is_invariants_safety_profile: bool = False
    ns_index_coupling_enabled: bool = False  # keep NS uncoupled for simplicity

    # The real profile exposes ns_driver_seat(rng); provide a stub.
    def ns_driver_seat(self, rng: random.Random) -> Seat:
        return "N"


def _profile_with_rs_north_pc_south() -> DummyProfile:
    """
    N has Random Suit, S has Partner Contingent, others unconstrained.
    """
    north_sub = DummySubProfile(
        random_suit_constraint=object(),
        partner_contingent_constraint=None,
        opponents_contingent_suit_constraint=None,
    )
    south_sub = DummySubProfile(
        random_suit_constraint=None,
        partner_contingent_constraint=object(),
        opponents_contingent_suit_constraint=None,
    )
    east_sub = DummySubProfile()   # unconstrained
    west_sub = DummySubProfile()   # unconstrained

    return DummyProfile(
        seat_profiles={
            "N": DummySeatProfile([north_sub]),
            "S": DummySeatProfile([south_sub]),
            "E": DummySeatProfile([east_sub]),
            "W": DummySeatProfile([west_sub]),
        },
        # Put N and S early in dealing order to make ordering visible.
        hand_dealing_order=["N", "E", "S", "W"],
        dealer="N",
    )


# --- The actual integration-style test ----------------------------------------


def test_random_suit_seat_matches_before_partner_contingent(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Integration-ish check: in _build_single_constrained_deal, seats whose
    chosen subprofile has Random Suit must be matched *before* seats whose
    chosen subprofile has Partner Contingent.

    We use dummy seat/profile types + a stub _match_seat to observe the order
    in which the engine processes seats, without caring about real cards or
    real constraint objects.
    """
    profile = _profile_with_rs_north_pc_south()

    # Make deal_generator treat DummySeatProfile as its SeatProfile type so
    # isinstance(seat_profile, SeatProfile) checks succeed.
    monkeypatch.setattr(deal_generator, "SeatProfile", DummySeatProfile)

    calls: List[tuple[Seat, bool, bool]] = []

    def fake_match_seat(
        profile: Any,
        seat: Seat,
        hand: List[Any],
        seat_profile: Any,
        chosen_subprofile: Any,
        chosen_subprofile_index_1based: int,
        random_suit_choices: Dict[Seat, List[str]],
        rng: random.Random,
    ) -> tuple[bool, Optional[List[str]]]:
        has_rs = getattr(chosen_subprofile, "random_suit_constraint", None) is not None
        has_pc = getattr(chosen_subprofile, "partner_contingent_constraint", None) is not None
        calls.append((seat, has_rs, has_pc))
        # Always "match" so we succeed on the first attempt; RS/PC ordering
        # is all we care about.
        return True, None

    monkeypatch.setattr(deal_generator, "_match_seat", fake_match_seat)

    rng = random.Random(1234)
    deal_generator._build_single_constrained_deal(rng, profile, board_number=1)

    # Extract the first occurrence of the RS seat and the PC seat from calls.
    rs_index: Optional[int] = None
    pc_index: Optional[int] = None

    for i, (seat, has_rs, has_pc) in enumerate(calls):
        if has_rs and rs_index is None:
            rs_index = i
        if has_pc and pc_index is None:
            pc_index = i

    # Sanity: both must have been seen.
    assert rs_index is not None, f"No Random Suit seat observed in calls: {calls!r}"
    assert pc_index is not None, f"No Partner Contingent seat observed in calls: {calls!r}"

    # Core property: RS seat must be matched before PC seat.
    assert rs_index < pc_index, f"Expected RS seat to be matched before PC seat, got call order {calls!r}"