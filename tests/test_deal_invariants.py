# tests/test_deal_invariants.py
from __future__ import annotations

from typing import List

import pytest

from bridge_engine.deal_generator import generate_deals
from bridge_engine.setup_env import run_setup


def test_deal_generator_invariants_no_duplication_or_loss(
    tmp_path,
    make_valid_profile,
) -> None:
    """
    Safety net: generated deals must be complete and non-overlapping.

    For a simple known-valid profile (make_valid_profile), generate 20 deals
    with a deterministic setup and assert for each deal:

      • Exactly 4 hands
      • Each hand has 13 cards
      • Total cards across all 4 hands == 52
      • All 52 cards are unique (no duplication or loss)
    """
    profile = make_valid_profile()

    # Use Section A's real setup helper so we're exercising the true pipeline.
    # use_seeded_default=True gives a deterministic seed.
    setup = run_setup(
        base_dir=tmp_path,
        owner="TestOwner",
        profile_name=profile.profile_name,
        ask_seed_choice=False,
        use_seeded_default=True,
    )

    num_deals = 20
    deal_set = generate_deals(setup, profile, num_deals)

    # Sanity: correct number of deals
    assert len(deal_set.deals) == num_deals

    for deal in deal_set.deals:
        # Deal.hands is Dict[Seat, List[Card]]
        hands: List[list[str]] = list(deal.hands.values())

        # Exactly 4 hands (one per seat)
        assert len(hands) == 4, "Each deal must have 4 hands"

        # Each hand has 13 cards
        for hand in hands:
            assert len(hand) == 13, "Each hand must contain 13 cards"

        # Flatten all cards
        all_cards = [card for hand in hands for card in hand]

        # Exactly 52 cards total
        assert len(all_cards) == 52, "Each deal must contain exactly 52 cards"

        # No duplicates
        assert len(set(all_cards)) == 52, "No duplicate cards allowed in a deal"
