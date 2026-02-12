import random
from typing import Dict

from bridge_engine.deal_generator import _build_single_board_random_suit_w_only
from tests.test_deal_generator_section_c import (  # type: ignore
    _random_suit_w_partner_contingent_e_profile,
)


def test_random_suit_profile_smoke_builds_valid_deal() -> None:
    """
    Small integration-ish smoke test for the Random Suit + Partner-Contingent
    profile. We don't micro-manage exact suit lengths here; instead we assert
    that the dedicated RS helper can build a well-formed deal for the
    known Test_RandomSuit_W_PC_E profile.

    This is intentionally light-weight but exercises the actual RS-specific
    pipeline (_build_single_board_random_suit_w_only) with real profile data.
    """
    profile = _random_suit_w_partner_contingent_e_profile()
    rng = random.Random(424242)

    deal = _build_single_board_random_suit_w_only(
        rng=rng,
        profile=profile,
        board_number=1,
    )

    # Basic invariants: four seats, 13 cards each, 52 unique cards.
    assert set(deal.hands.keys()) == {"N", "E", "S", "W"}

    hand_lengths = [len(hand) for hand in deal.hands.values()]
    assert hand_lengths == [13, 13, 13, 13]

    all_cards = [card for hand in deal.hands.values() for card in hand]
    assert len(all_cards) == 52
    assert len(set(all_cards)) == 52