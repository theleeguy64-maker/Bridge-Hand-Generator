from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Dict, List

import pytest

from bridge_engine import deal_generator
from bridge_engine.deal_generator import _build_single_constrained_deal


Seat = str  # keep type hints readable


@dataclass
class DummySubProfile:
    """Minimal subprofile with optional RS/PC flags.

    We don't care about real constraint dataclasses here – just whether a seat
    *has* Random Suit or Partner Contingent in the generator's eyes.
    """
    has_random_suit: bool = False
    has_partner_contingent: bool = False

    # The generator checks for these attributes by duck-typing.
    @property
    def random_suit_constraint(self):
        return object() if self.has_random_suit else None

    @property
    def partner_contingent_constraint(self):
        return object() if self.has_partner_contingent else None

    @property
    def opponents_contingent_suit_constraint(self):
        return None


class DummySeatProfile:
    """Just enough shape for deal_generator to treat this as a SeatProfile."""

    def __init__(self, subprofiles: List[DummySubProfile]):
        self.subprofiles = list(subprofiles)


class DummyProfile:
    """HandProfile-shaped object with only the fields we actually need."""

    def __init__(self):
        # W has Random Suit, E has Partner Contingent, N/S are boring.
        self.seat_profiles: Dict[Seat, DummySeatProfile] = {
            "W": DummySeatProfile([DummySubProfile(has_random_suit=True)]),
            "E": DummySeatProfile([DummySubProfile(has_partner_contingent=True)]),
            "N": DummySeatProfile([DummySubProfile()]),
            "S": DummySeatProfile([DummySubProfile()]),
        }
        self.dealer: Seat = "W"
        self.hand_dealing_order: List[Seat] = ["W", "N", "E", "S"]

        # Make sure we stay on the full constrained path.
        self.is_invariants_safety_profile = False
        self.ns_index_coupling_enabled = False

    # Called only when ns_index_coupling_enabled is True; keep for safety.
    def ns_driver_seat(self, rng: random.Random) -> Seat:
        return "N"


def test_rs_pc_order_w_before_e_and_pc_sees_rs_choice(monkeypatch) -> None:
    """
    For a profile where West has Random Suit and East has Partner Contingent,
    _build_single_constrained_deal should:

      * call _match_seat for West before East, and
      * ensure East's _match_seat invocation can "see" West's RS choice via
        random_suit_choices["W"].

    We don't exercise the real RS/PC dataclasses here – we simulate RS/PC via a
    fake _match_seat and a DummyProfile, purely to test order and visibility.
    """
    profile = DummyProfile()

    # Make the generator treat DummySeatProfile as its SeatProfile type.
    monkeypatch.setattr(deal_generator, "SeatProfile", DummySeatProfile)

    call_order: List[Seat] = []
    rs_snapshot_seen_at_e: Dict[Seat, List[str]] | None = None

    def fake_match_seat(
        *,
        profile,
        seat: Seat,
        hand,
        seat_profile,
        chosen_subprofile,
        chosen_subprofile_index_1based: int,
        random_suit_choices: Dict[Seat, List[str]],
        rng: random.Random,
    ):
        nonlocal rs_snapshot_seen_at_e

        call_order.append(seat)

        # Simulate West being the Random Suit seat: choose "S" and record it.
        if seat == "W":
            random_suit_choices["W"] = ["S"]
            # We "matched", and return a dummy RS choice payload.
            return True, ["S"], None

        # Simulate East being Partner Contingent on West's RS choice.
        if seat == "E":
            # Take a snapshot of what East can see.
            rs_snapshot_seen_at_e = dict(random_suit_choices)
            # For the purposes of this test, succeed only if we can see W -> ["S"].
            ok = random_suit_choices.get("W") == ["S"]
            return ok, None, None

        # Other seats are unconstrained and always match.
        return True, None, None

    # Patch _match_seat inside the generator module.
    monkeypatch.setattr(deal_generator, "_match_seat", fake_match_seat)

    rng = random.Random(12345)

    # If the RS/PC ordering is wrong, either:
    #   * West won't run before East, or
    #   * East won't see random_suit_choices["W"] == ["S"],
    # and the board will fail to construct (raising DealGenerationError).
    deal = _build_single_constrained_deal(rng=rng, profile=profile, board_number=1)

    # Sanity: we did get a Deal object back.
    assert deal.dealer == "W"

    # 1) West must be evaluated before East in the matching order.
    assert "W" in call_order and "E" in call_order
    assert call_order.index("W") < call_order.index("E")

    # 2) When East ran, it must have seen West's RS choice already present.
    assert rs_snapshot_seen_at_e is not None
    assert rs_snapshot_seen_at_e.get("W") == ["S"]