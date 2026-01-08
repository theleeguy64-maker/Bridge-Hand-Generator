# test_deal_generator_section_c.py

from __future__ import annotations
from typing import Dict, List

import random

from bridge_engine.deal_generator import (
    generate_deals,
    VULNERABILITY_SEQUENCE,
)

from bridge_engine.hand_profile import (
    HandProfile,
    SeatProfile,
    SubProfile,
    StandardSuitConstraints,
    RandomSuitConstraintData,
    PartnerContingentData,
    SuitRange,
)
from bridge_engine.setup_env import run_setup

from bridge_engine.deal_generator import (
    generate_deals,
    DealGenerationError,
    _build_single_constrained_deal,  # <-- add this if not already imported
)


def _wide_suit_range() -> SuitRange:
    return SuitRange(min_cards=0, max_cards=13, min_hcp=0, max_hcp=37)


def _wide_standard(total_min: int = 0, total_max: int = 37) -> StandardSuitConstraints:
    sr = _wide_suit_range()
    return StandardSuitConstraints(
        spades=sr,
        hearts=sr,
        diamonds=sr,
        clubs=sr,
        total_min_hcp=total_min,
        total_max_hcp=total_max,
    )


def _simple_standard_only_profile() -> HandProfile:
    """
    Very loose Standard-only profile:
      - All suits 0–13 cards, 0–37 HCP
      - Total HCP 0–37
      - All four seats constrained identically
    This exercises the constrained path without being restrictive.
    """
    seat_profiles: Dict[str, SeatProfile] = {}
    for seat in ("N", "E", "S", "W"):
        sub = SubProfile(
            standard=_wide_standard(),
            random_suit_constraint=None,
            partner_contingent_constraint=None,
        )
        seat_profiles[seat] = SeatProfile(seat=seat, subprofiles=[sub])

    return HandProfile(
        profile_name="Test_StandardOnly",
        description="Simple standard-only test profile",
        dealer="N",
        hand_dealing_order=["N", "E", "S", "W"],
        tag="Opener",          # must be 'Opener' or 'Overcaller'
        author="Test",
        version="0.1",
        seat_profiles=seat_profiles,
    )


def _random_suit_w_partner_contingent_e_profile() -> HandProfile:
    """
    Profile to exercise:
      - Random Suit constraint on West (1 suit from S/H, 5+ cards)
      - Partner Contingent constraint on East (>=1 card in West's chosen suit)
      - N and S are wide standard-only
    Dealer: W
    Dealing order: W -> N -> S -> E
    """
    # West: Random Suit in S/H, 5+ cards in chosen suit
    rs = RandomSuitConstraintData(
        required_suits_count=1,
        allowed_suits=["S", "H"],
        suit_ranges=[SuitRange(min_cards=5, max_cards=13, min_hcp=0, max_hcp=37)],
        pair_overrides=[],
    )
    west_std = _wide_standard()
    west_sub = SubProfile(
        standard=west_std,
        random_suit_constraint=rs,
        partner_contingent_constraint=None,
    )
    west_profile = SeatProfile(seat="W", subprofiles=[west_sub])

    # East: Partner Contingent on W's chosen suit; at least 1 card
    pc = PartnerContingentData(
        partner_seat="W",
        suit_range=SuitRange(min_cards=1, max_cards=13, min_hcp=0, max_hcp=37),
    )
    east_std = _wide_standard()
    east_sub = SubProfile(
        standard=east_std,
        random_suit_constraint=None,
        partner_contingent_constraint=pc,
    )
    east_profile = SeatProfile(seat="E", subprofiles=[east_sub])

    # North and South: simple wide Standard-only profiles
    north_sub = SubProfile(
        standard=_wide_standard(),
        random_suit_constraint=None,
        partner_contingent_constraint=None,
    )
    south_sub = SubProfile(
        standard=_wide_standard(),
        random_suit_constraint=None,
        partner_contingent_constraint=None,
    )
    north_profile = SeatProfile(seat="N", subprofiles=[north_sub])
    south_profile = SeatProfile(seat="S", subprofiles=[south_sub])

    seat_profiles: Dict[str, SeatProfile] = {
        "N": north_profile,
        "E": east_profile,
        "S": south_profile,
        "W": west_profile,
    }

    return HandProfile(
        profile_name="Test_RandomSuit_W_PC_E",
        description="Random Suit for W, Partner Contingent for E",
        dealer="W",
        hand_dealing_order=["W", "N", "S", "E"],
        tag="Overcaller",      # must be 'Opener' or 'Overcaller'
        author="Test",
        version="0.1",
        seat_profiles=seat_profiles,
    )


def _count_cards(hand: List[str]) -> int:
    return len(hand)


def _suits_of(hand: List[str]) -> Dict[str, List[str]]:
    suits = {"S": [], "H": [], "D": [], "C": []}
    for card in hand:
        if len(card) != 2:
            continue
        r, s = card[0], card[1]
        if s in suits:
            suits[s].append(r)
    return suits


def test_generate_deals_with_standard_only_profile(tmp_path) -> None:
    base_dir = tmp_path / "out"
    profile = _simple_standard_only_profile()

    setup = run_setup(
        base_dir=base_dir,
        owner="TestOwner",
        profile_name=profile.profile_name,
        ask_seed_choice=False,
    )

    num_deals = 5
    deal_set = generate_deals(setup, profile, num_deals)

    assert len(deal_set.deals) == num_deals

    for deal in deal_set.deals:
        # each deal must have four seats
        assert set(deal.hands.keys()) == {"N", "E", "S", "W"}
        # 13 cards per hand, 52 unique cards total
        all_cards: List[str] = []
        for hand in deal.hands.values():
            assert _count_cards(hand) == 13
            all_cards.extend(hand)
        assert len(all_cards) == 52
        assert len(set(all_cards)) == 52

        # dealer after rotation must be N or S (given initial dealer N)
        assert deal.dealer in ("N", "S")
        # vulnerability must be in the known sequence
        assert deal.vulnerability in VULNERABILITY_SEQUENCE


def test_random_suit_w_has_long_suit(tmp_path) -> None:
    """
    Check that the original West hand (before possible rotation)
    always satisfies the Random Suit constraint: at least one long
    (>=5 cards) S/H suit.
    """
    base_dir = tmp_path / "out_rs"
    profile = _random_suit_w_partner_contingent_e_profile()

    setup = run_setup(
        base_dir=base_dir,
        owner="TestOwner",
        profile_name=profile.profile_name,
        ask_seed_choice=False,
    )

    num_deals = 8
    deal_set = generate_deals(setup, profile, num_deals)

    assert len(deal_set.deals) == num_deals

    for deal in deal_set.deals:
        # Original dealer is W. After rotation, dealer becomes E.
        rotated = (deal.dealer == "E")

        if rotated:
            # West's original hand ended up at East after rotation.
            west_original_hand = deal.hands["E"]
        else:
            west_original_hand = deal.hands["W"]

        suits = _suits_of(west_original_hand)
        long_suits = [s for s in ("S", "H") if len(suits[s]) >= 5]
        assert long_suits, (
            f"Original West hand has no long S/H suit in deal {deal.board_number}"
        )
        