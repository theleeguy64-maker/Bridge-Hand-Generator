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
        
        
def test_constructive_help_default_disabled() -> None:
    """
    By default, constructive help should be disabled so behaviour matches
    the original pure-random generator unless explicitly opted-in.
    """
    assert deal_generator.ENABLE_CONSTRUCTIVE_HELP is False


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
        # Signature: _match_seat(...) -> (matched: bool, chosen_random_suit)
        return True, None

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

    # Explicitly disable constructive help (even though the default is False).
    monkeypatch.setattr(deal_generator, "ENABLE_CONSTRUCTIVE_HELP", False)

    rng = random.Random(1234)
    deal = _build_single_constrained_deal(rng, profile, board_number=1)

    # Sanity check: we actually built *some* deal, i.e. the function returns.
    assert deal is not None
    assert set(deal.hands.keys()) == {"N", "E", "S", "W"}
    assert all(len(hand) == 13 for hand in deal.hands.values())
    
    
def test_constructive_help_skips_unviable_help_seat(monkeypatch) -> None:
    """
    If the hardest seat is currently classified as 'unviable', constructive
    help should *not* call _construct_hand_for_seat, even when the global
    flag is enabled.

    This test stubs:
      - _choose_hardest_seat_for_board  -> always "N"
      - _summarize_profile_viability    -> marks "N" as unviable
      - _construct_hand_for_seat        -> increments a counter if ever used
      - _match_seat                     -> always matches (so the board builds)
    """

    # Safety: ensure we start from a known flag value then override in test.
    monkeypatch.setattr(deal_generator, "ENABLE_CONSTRUCTIVE_HELP", True)

    # Make the generator treat DummySeatProfile as its SeatProfile type.
    # (Assumes DummySeatProfile / DummyProfile are already defined in this file,
    #  mirroring the other tests here.)
    monkeypatch.setattr(deal_generator, "SeatProfile", DummySeatProfile)

    profile = DummyProfile()  # standard-only dummy

    # Force the hardest-seat chooser to always pick North.
    def fake_choose_hardest_seat_for_board(
        profile,
        seat_fail_counts,
        seat_seen_counts,
        dealing_order,
        attempt_number,
        cfg,
    ):
        return "N"

    monkeypatch.setattr(
        deal_generator,
        "_choose_hardest_seat_for_board",
        fake_choose_hardest_seat_for_board,
    )

    # Force the viability summary to mark N as "unviable" (others arbitrary).
    def fake_summarize_profile_viability(seat_fail_counts, seat_seen_counts):
        return {"N": "unviable", "E": "likely", "S": "likely", "W": "likely"}

    monkeypatch.setattr(
        deal_generator,
        "_summarize_profile_viability",
        fake_summarize_profile_viability,
    )

    # Count how many times constructive helper is invoked.
    construct_calls = {"count": 0}

    def fake_construct_hand_for_seat(rng, deck, min_suit_counts):
        construct_calls["count"] += 1
        # Behave like a simple random-draw helper so the rest of the pipeline
        # still works: take 13 cards from the deck.
        hand = list(deck[:13])
        del deck[:13]
        return hand

    monkeypatch.setattr(
        deal_generator,
        "_construct_hand_for_seat",
        fake_construct_hand_for_seat,
    )

    # Make every seat match so we actually get a deal and exit the loop.
    def always_match_seat(
        profile,
        seat,
        hand,
        seat_profile,
        chosen_subprofile,
        chosen_subprofile_index_1based,
        random_suit_choices,
        rng,
    ):
        return True, None

    monkeypatch.setattr(deal_generator, "_match_seat", always_match_seat)

    rng = random.Random(42)
    deal = deal_generator._build_single_constrained_deal(
        rng=rng,
        profile=profile,
        board_number=1,
    )

    # We should have successfully produced a deal...
    assert deal is not None
    # ...without ever calling the constructive helper for an 'unviable' seat.
    assert construct_calls["count"] == 0
    