# tests/test_random_suit_pc_order.py

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import random
import pytest

from bridge_engine import deal_generator

Seat = str


@dataclass
class DummySubProfile:
    """Minimal subprofile shape for RS / PC detection."""
    has_rs: bool = False
    has_pc: bool = False

    def __post_init__(self) -> None:
        # These are the only three attributes _seat_has_nonstandard_constraints
        # and the RS/PC ordering logic care about.
        self.random_suit_constraint = object() if self.has_rs else None
        self.partner_contingent_constraint = object() if self.has_pc else None
        self.opponents_contingent_suit_constraint = None


class DummySeatProfile:
    """Duck-typed SeatProfile replacement with just .subprofiles."""

    def __init__(self, subprofiles: List[DummySubProfile]) -> None:
        self.subprofiles = list(subprofiles)


class DummyProfile:
    """
    Minimal profile for exercising RS/PC ordering inside
    _build_single_constrained_deal.

    West ("W") is the Random-Suit seat.
    East ("E") is the Partner-Contingent seat that depends on West.
    """

    def __init__(self) -> None:
        self.seat_profiles: Dict[Seat, DummySeatProfile] = {
            "W": DummySeatProfile([DummySubProfile(has_rs=True)]),
            "E": DummySeatProfile([DummySubProfile(has_pc=True)]),
        }
        # Ensure both W and E are in the dealing order so they get processed.
        self.hand_dealing_order: List[Seat] = ["W", "E", "N", "S"]
        self.dealer: Seat = "W"

        # No invariants fast-path.
        self.is_invariants_safety_profile = False

        # Keep NS coupling effectively disabled for this dummy profile.
        self.ns_index_coupling_enabled = False

    def ns_driver_seat(self, rng: random.Random) -> Seat:
        # Not relevant for this test, but _select_subprofiles_for_board expects it.
        return "N"


def test_partner_contingent_sees_partner_random_suit_choice(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Sanity check on evaluation order inside _build_single_constrained_deal:

      * West ("W") is treated as a Random Suit seat.
      * East ("E") is treated as a Partner-Contingent seat.

    The deal builder should:

      1. Call _match_seat for W *before* calling it for E.
      2. Allow W's _match_seat call to record its RS choice into
         random_suit_choices["W"].
      3. When E's _match_seat runs, random_suit_choices["W"] must already
         contain that RS choice.

    This test does not rely on the real RandomSuitConstraint / PC semantics;
    it only asserts the ordering and the flow of RS information via
    random_suit_choices.
    """
    profile = DummyProfile()

    # Make the generator treat DummySeatProfile as its SeatProfile type.
    monkeypatch.setattr(deal_generator, "SeatProfile", DummySeatProfile)

    call_order: List[Seat] = []
    seen_rs_choices_at_e: Optional[List[str]] = None

    def fake_match_seat(
        *,
        profile: Any,
        seat: Seat,
        hand: List[Any],
        seat_profile: Any,
        chosen_subprofile: Any,
        chosen_subprofile_index_1based: int,
        random_suit_choices: Dict[Seat, List[str]],
        rng: random.Random,
    ):
        nonlocal seen_rs_choices_at_e

        call_order.append(seat)

        if seat == "W":
            # Simulate West's Random Suit choosing "S" (Spades) and
            # recording that choice in the shared dict, as the real RS
            # logic would do.
            random_suit_choices.setdefault("W", []).append("S")
            return True, ["S"]

        if seat == "E":
            # Partner-contingent seat must "see" West's RS choice by the
            # time its matcher is called.
            seen_rs_choices_at_e = list(random_suit_choices.get("W", []))
            return True, None

        # Unconstrained / irrelevant seats: always match.
        return True, None
        
        # Unconstrained / irrelevant seats: always match.
        return True, None

    monkeypatch.setattr(deal_generator, "_match_seat", fake_match_seat)

    rng = random.Random(1234)

    # If ordering is wrong, either:
    #   * the assertions in fake_match_seat will fail, or
    #   * we won't reach a successful deal.
    deal = deal_generator._build_single_constrained_deal(
        rng=rng,
        profile=profile,
        board_number=1,
    )

    # Basic sanity: a deal was produced.
    assert deal is not None

    # 1) West must be matched before East.
    assert "W" in call_order and "E" in call_order
    assert call_order.index("W") < call_order.index("E")

    # 2) By the time East ran, it must have seen West's RS choice.
    assert seen_rs_choices_at_e == ["S"]