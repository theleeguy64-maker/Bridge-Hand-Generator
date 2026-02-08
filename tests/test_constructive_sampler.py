# tests/test_constructive_sampler.py

from __future__ import annotations

import random
from typing import List

from bridge_engine.deal_generator import _build_deck, _construct_hand_for_seat, Card


def _count_suit(hand: List[Card], suit: str) -> int:
    return sum(1 for c in hand if str(c).endswith(suit))


def test_constructive_hand_respects_minima_and_mutates_deck() -> None:
    rng = random.Random(12345)
    deck = _build_deck()
    rng.shuffle(deck)

    original_len = len(deck)
    assert original_len >= 13

    minima = {"S": 4, "H": 3}

    hand = _construct_hand_for_seat(rng, deck, minima)

    # Hand shape
    assert len(hand) == 13
    assert _count_suit(hand, "S") >= 4
    assert _count_suit(hand, "H") >= 3

    # Deck was shrunk and no selected card remains in the deck.
    assert len(deck) == original_len - 13
    assert len(set(hand)) == len(hand)
    assert not (set(hand) & set(deck))


def test_constructive_handles_insufficient_suit_cards_gracefully() -> None:
    rng = random.Random(2025)

    # Synthetic small deck: only 2 "spades", enough other cards to reach 13.
    deck: List[Card] = [
        "AS",
        "KS",  # 2 spades
        "AH",
        "KH",
        "QH",
        "JH",
        "AD",
        "KD",
        "QD",
        "JD",
        "AC",
        "KC",
        "QC",
        "JC",
    ]
    original_len = len(deck)
    assert original_len >= 13

    minima = {"S": 5}  # ask for more spades than exist

    hand = _construct_hand_for_seat(rng, deck, minima)

    # We should end up with "as many as possible" spades, not crash.
    assert _count_suit(hand, "S") == 2
    assert len(hand) == 13
    assert len(deck) == original_len - 13
    assert len(set(hand)) == len(hand)
    assert not (set(hand) & set(deck))