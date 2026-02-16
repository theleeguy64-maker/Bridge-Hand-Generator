# tests/test_constructive_help_gate.py

from __future__ import annotations

import random
from typing import Dict, List

import pytest

from bridge_engine import deal_generator
from bridge_engine.deal_generator import _build_single_constrained_deal


class DummySubProfile:
    """Minimal subprofile: no non-standard constraints."""

    def __init__(self) -> None:
        self.random_suit_constraint = None
        self.partner_contingent_constraint = None
        self.opponents_contingent_suit_constraint = None


class DummySeatProfile:
    """SeatProfile-like object with a single, unconstrained subprofile."""

    def __init__(self) -> None:
        self.subprofiles: List[DummySubProfile] = [DummySubProfile()]


class DummyProfile:
    """
    Profile with no invariants fast-path and only standard constraints,
    suitable for exercising the main constrained loop.
    """

    def __init__(self) -> None:
        self.profile_name = "Dummy"
        self.dealer = "N"
        self.hand_dealing_order = ["N", "E", "S", "W"]

        self.seat_profiles: Dict[str, DummySeatProfile] = {
            "N": DummySeatProfile(),
            "E": DummySeatProfile(),
            "S": DummySeatProfile(),
            "W": DummySeatProfile(),
        }

        # Ensure we do NOT take the invariants fast-path.
        self.is_invariants_safety_profile = False

        # Used by the NS index-coupling logic; trivial implementation is fine.
        def _ns_driver_seat(rng: random.Random) -> str:
            return "N"

        self.ns_driver_seat = _ns_driver_seat


def test_constructive_help_gate_does_not_call_choose_hardest(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    When ENABLE_CONSTRUCTIVE_HELP is False, the main constrained loop must not
    call _choose_hardest_seat_for_board.

    We enforce this by monkeypatching _choose_hardest_seat_for_board to raise
    if it is ever invoked, then running _build_single_constrained_deal on a
    simple profile where _match_seat always succeeds on the first attempt.
    """
    profile = DummyProfile()

    # Make deal_generator treat DummySeatProfile as its SeatProfile type.
    monkeypatch.setattr(deal_generator, "SeatProfile", DummySeatProfile)

    # All seats always match so we succeed on the first attempt and never
    # exhaust MAX_BOARD_ATTEMPTS.
    def always_match(*args, **kwargs):
        # Signature: _match_seat(...) -> (matched: bool, chosen_random_suit, fail_reason)
        return True, None, None

    monkeypatch.setattr(deal_generator, "_match_seat", always_match)

    # If constructive help tried to consult _choose_hardest_seat_for_board,
    # this will blow up the test.
    def fail_if_called(*args, **kwargs):
        raise AssertionError(
            "_choose_hardest_seat_for_board should not be called "
            "when ENABLE_CONSTRUCTIVE_HELP is False and the board "
            "completes in the normal success path."
        )

    monkeypatch.setattr(
        deal_generator,
        "_choose_hardest_seat_for_board",
        fail_if_called,
    )

    rng = random.Random(1234)
    deal = _build_single_constrained_deal(rng, profile, board_number=1)

    # Sanity check: we actually built *some* deal, i.e. the function returns.
    assert deal is not None
    assert set(deal.hands.keys()) == {"N", "E", "S", "W"}
    assert all(len(hand) == 13 for hand in deal.hands.values())
