import random
from types import SimpleNamespace

from bridge_engine.seat_viability import _match_random_suit_with_attempt


def test_match_random_suit_with_attempt_returns_choice_on_failure():
    # Analysis where Spades always fails (0 cards, 0 HCP).
    analysis = SimpleNamespace(
        cards_by_suit={"S": [], "H": [], "D": [], "C": []},
        hcp_by_suit={"S": 0, "H": 0, "D": 0, "C": 0},
    )

    # RS constraint that will choose Spades and then fail min_cards.
    sr = SimpleNamespace(min_cards=1, max_cards=13, min_hcp=0, max_hcp=37)
    rs = SimpleNamespace(
        allowed_suits=["S"],
        required_suits_count=1,
        suit_ranges=[sr],
        pair_overrides=[],
    )

    rng = random.Random(0)

    matched, chosen = _match_random_suit_with_attempt(analysis, rs, rng)

    assert matched is False
    assert chosen == ["S"]