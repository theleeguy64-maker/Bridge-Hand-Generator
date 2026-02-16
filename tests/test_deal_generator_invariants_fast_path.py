# tests/test_deal_generator_invariants_fast_path.py

from __future__ import annotations

from typing import Any
import random

from bridge_engine import deal_generator


class _DummyInvariantsProfile:
    """
    Minimal dummy profile that:
      * looks enough like a HandProfile for _build_single_constrained_deal
      * is tagged as an invariants-safety profile
      * has NO non-standard constraints (seat_profiles are plain objects)
    """

    def __init__(self) -> None:
        self.profile_name = "Dummy invariants profile"
        self.description = "Guard test invariants fast path profile"
        self.dealer = "N"
        self.hand_dealing_order = ["N", "E", "S", "W"]
        # Values are NOT SeatProfile instances -> has_nonstandard == False
        self.seat_profiles = {
            "N": object(),
            "E": object(),
            "S": object(),
            "W": object(),
        }
        # This is the key metadata flag the fast path checks
        self.is_invariants_safety_profile = True


def test_invariants_safety_profile_uses_fast_path(monkeypatch) -> None:
    """
    Guard test: profiles tagged is_invariants_safety_profile must NOT go
    through the slow constrained path inside _build_single_constrained_deal.

    We enforce this by monkeypatching _match_seat to explode if it is ever
    called. If the fast path is wired correctly, _build_single_constrained_deal
    will:
      * skip all constraint matching,
      * never call _match_seat,
      * and still return a complete, well-formed Deal.
    """

    # If the constrained pipeline is used, this will be called and the
    # test will fail loudly.
    def boom_match_seat(*args: Any, **kwargs: Any) -> None:  # pragma: no cover
        raise AssertionError("_match_seat should not be called for invariants-safety fast path")

    monkeypatch.setattr(deal_generator, "_match_seat", boom_match_seat)

    rng = random.Random(123)
    profile = _DummyInvariantsProfile()

    # Call the internal helper directly; generate_deals(...) just loops this.
    deal = deal_generator._build_single_constrained_deal(
        rng=rng,
        profile=profile,  # type: ignore[arg-type]
        board_number=1,
    )

    # Sanity-check we got a well-formed deal and not some stub.
    assert deal.board_number == 1
    assert deal.dealer == profile.dealer
    assert set(deal.hands.keys()) == set(profile.hand_dealing_order)

    all_cards = [card for hand in deal.hands.values() for card in hand]
    assert len(all_cards) == 52
    assert len(set(all_cards)) == 52
