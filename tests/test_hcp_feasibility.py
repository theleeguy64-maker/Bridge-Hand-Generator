# tests/test_hcp_feasibility.py
"""
Unit tests for HCP feasibility utilities (TODO #5).

Tests call the functions directly — no dependency on the ENABLE_HCP_FEASIBILITY_CHECK
gate flag.  These prove the math works regardless of whether the gate is on or off.
"""
from __future__ import annotations

import math
import pytest

from bridge_engine.deal_generator import (
    _card_hcp,
    _deck_hcp_stats,
    _check_hcp_feasibility,
    _build_deck,
)


# ---------------------------------------------------------------------------
# _card_hcp tests
# ---------------------------------------------------------------------------

class TestCardHcp:
    """Verify HCP values for all rank categories."""

    def test_ace_is_4(self):
        assert _card_hcp("AS") == 4
        assert _card_hcp("AH") == 4

    def test_king_is_3(self):
        assert _card_hcp("KS") == 3
        assert _card_hcp("KD") == 3

    def test_queen_is_2(self):
        assert _card_hcp("QC") == 2
        assert _card_hcp("QH") == 2

    def test_jack_is_1(self):
        assert _card_hcp("JS") == 1
        assert _card_hcp("JD") == 1

    def test_ten_is_0(self):
        assert _card_hcp("TS") == 0

    def test_spot_cards_are_0(self):
        for rank in "98765432":
            assert _card_hcp(f"{rank}S") == 0, f"Rank {rank} should be 0 HCP"

    def test_empty_string_is_0(self):
        assert _card_hcp("") == 0


# ---------------------------------------------------------------------------
# _deck_hcp_stats tests
# ---------------------------------------------------------------------------

class TestDeckHcpStats:
    """Verify aggregate HCP statistics for decks of various sizes."""

    def test_full_deck_sums(self):
        """Full 52-card deck: hcp_sum=40, hcp_sum_sq=120."""
        deck = _build_deck()
        hcp_sum, hcp_sum_sq = _deck_hcp_stats(deck)
        assert hcp_sum == 40
        # 4 aces (4²=16 each) + 4 kings (3²=9) + 4 queens (2²=4) + 4 jacks (1²=1) + 36 spots (0)
        # = 4*16 + 4*9 + 4*4 + 4*1 = 64 + 36 + 16 + 4 = 120
        assert hcp_sum_sq == 120

    def test_empty_deck(self):
        hcp_sum, hcp_sum_sq = _deck_hcp_stats([])
        assert hcp_sum == 0
        assert hcp_sum_sq == 0

    def test_partial_deck_only_honors(self):
        """Deck with just the 4 aces."""
        deck = ["AS", "AH", "AD", "AC"]
        hcp_sum, hcp_sum_sq = _deck_hcp_stats(deck)
        assert hcp_sum == 16      # 4 * 4
        assert hcp_sum_sq == 64   # 4 * 16

    def test_partial_deck_mixed(self):
        """Deck with A, K, 5, 2 of spades."""
        deck = ["AS", "KS", "5S", "2S"]
        hcp_sum, hcp_sum_sq = _deck_hcp_stats(deck)
        assert hcp_sum == 7        # 4 + 3 + 0 + 0
        assert hcp_sum_sq == 25    # 16 + 9 + 0 + 0

    def test_single_spot_card(self):
        hcp_sum, hcp_sum_sq = _deck_hcp_stats(["7H"])
        assert hcp_sum == 0
        assert hcp_sum_sq == 0


# ---------------------------------------------------------------------------
# _check_hcp_feasibility tests
# ---------------------------------------------------------------------------

class TestCheckHcpFeasibility:
    """Verify the statistical feasibility check for various scenarios."""

    # -- Feasible cases --

    def test_feasible_wide_range_full_deck(self):
        """Drawing 13 cards from a full deck, target 5-15: trivially feasible."""
        deck = _build_deck()
        hcp_sum, hcp_sum_sq = _deck_hcp_stats(deck)
        assert _check_hcp_feasibility(
            drawn_hcp=0, cards_remaining=13,
            deck_size=52, deck_hcp_sum=hcp_sum, deck_hcp_sum_sq=hcp_sum_sq,
            target_min=5, target_max=15,
        ) is True

    def test_feasible_tight_range_at_expected_value(self):
        """Target 9-11 with full deck: expected = 10, feasible."""
        deck = _build_deck()
        hcp_sum, hcp_sum_sq = _deck_hcp_stats(deck)
        assert _check_hcp_feasibility(
            drawn_hcp=0, cards_remaining=13,
            deck_size=52, deck_hcp_sum=hcp_sum, deck_hcp_sum_sq=hcp_sum_sq,
            target_min=9, target_max=11,
        ) is True

    def test_feasible_after_moderate_prealloc(self):
        """Pre-allocated 3 HCP from 3 cards, 10 remaining from 49-card deck.
        Target 10-12.  Expected additional ~7.55 → total ~10.55, within range."""
        # Remove 3 cards worth 3 HCP (e.g., KS + two spots) from a 52-card deck.
        # Remaining: 49 cards, 37 HCP.
        # hcp_sum_sq for remaining: 120 - 9 = 111 (removed K=3, 3²=9)
        assert _check_hcp_feasibility(
            drawn_hcp=3, cards_remaining=10,
            deck_size=49, deck_hcp_sum=37, deck_hcp_sum_sq=111,
            target_min=10, target_max=12,
        ) is True

    # -- Reject-high cases --

    def test_reject_high_extreme_prealloc(self):
        """Pre-allocated 3 aces = 12 HCP from 3 cards, 10 remaining from 49.
        Remaining deck: 28 HCP, 49 cards.  Expected additional = 10*28/49 ≈ 5.71.
        Expected total ≈ 17.71.  ExpDown ≈ 14.67 — well above max of 12.
        hcp_sum_sq for remaining: 120 - 3*(4²) = 72."""
        assert _check_hcp_feasibility(
            drawn_hcp=12, cards_remaining=10,
            deck_size=49, deck_hcp_sum=28, deck_hcp_sum_sq=72,
            target_min=10, target_max=12,
        ) is False

    def test_reject_high_already_at_max(self):
        """Already drawn 15 HCP with 3 cards remaining.  Target 10-12.
        Even 0 additional HCP won't bring us under 12."""
        assert _check_hcp_feasibility(
            drawn_hcp=15, cards_remaining=3,
            deck_size=36, deck_hcp_sum=10, deck_hcp_sum_sq=30,
            target_min=10, target_max=12,
        ) is False

    # -- Reject-low cases --

    def test_reject_low_only_spots_remain(self):
        """All remaining cards are spots (0 HCP).  Need 10-12 but drawn only 2."""
        assert _check_hcp_feasibility(
            drawn_hcp=2, cards_remaining=10,
            deck_size=36, deck_hcp_sum=0, deck_hcp_sum_sq=0,
            target_min=10, target_max=12,
        ) is False

    def test_reject_low_insufficient_remaining(self):
        """Drawn 0 HCP, 2 cards remaining from a low-HCP deck (total 1 HCP).
        Expected additional ≈ 2 * (1/20) = 0.1.  Target 10-12 unreachable."""
        assert _check_hcp_feasibility(
            drawn_hcp=0, cards_remaining=2,
            deck_size=20, deck_hcp_sum=1, deck_hcp_sum_sq=1,
            target_min=10, target_max=12,
        ) is False

    # -- Edge cases --

    def test_exact_check_when_hand_complete(self):
        """cards_remaining=0: exact comparison, no statistics."""
        assert _check_hcp_feasibility(
            drawn_hcp=10, cards_remaining=0,
            deck_size=39, deck_hcp_sum=30, deck_hcp_sum_sq=90,
            target_min=10, target_max=12,
        ) is True

    def test_exact_check_when_hand_complete_out_of_range(self):
        """cards_remaining=0 but drawn_hcp outside target."""
        assert _check_hcp_feasibility(
            drawn_hcp=15, cards_remaining=0,
            deck_size=39, deck_hcp_sum=30, deck_hcp_sum_sq=90,
            target_min=10, target_max=12,
        ) is False

    def test_empty_deck_uses_exact_check(self):
        """deck_size=0: no cards to draw, just check drawn_hcp."""
        assert _check_hcp_feasibility(
            drawn_hcp=11, cards_remaining=0,
            deck_size=0, deck_hcp_sum=0, deck_hcp_sum_sq=0,
            target_min=10, target_max=12,
        ) is True

    def test_single_card_deck(self):
        """deck_size=1, cards_remaining=1: deterministic draw, no variance."""
        # The one remaining card is an Ace (4 HCP).  drawn_hcp=8.
        # Total will be exactly 8+4=12.  Target 10-12 → feasible.
        assert _check_hcp_feasibility(
            drawn_hcp=8, cards_remaining=1,
            deck_size=1, deck_hcp_sum=4, deck_hcp_sum_sq=16,
            target_min=10, target_max=12,
        ) is True

    def test_single_card_deck_out_of_range(self):
        """deck_size=1, cards_remaining=1: deterministic draw, but result out of range."""
        # The one remaining card is an Ace (4 HCP).  drawn_hcp=9.
        # Total will be exactly 9+4=13.  Target 10-12 → reject.
        assert _check_hcp_feasibility(
            drawn_hcp=9, cards_remaining=1,
            deck_size=1, deck_hcp_sum=4, deck_hcp_sum_sq=16,
            target_min=10, target_max=12,
        ) is False

    # -- Formula verification --

    def test_formula_reproduces_known_bridge_variance(self):
        """Full deck, 13 cards: Var(HCP) should be 290/17 ≈ 17.059.
        This is the well-known bridge result for a random hand."""
        deck = _build_deck()
        hcp_sum, hcp_sum_sq = _deck_hcp_stats(deck)
        d = 52
        r = 13

        mu = hcp_sum / d
        sigma_sq = hcp_sum_sq / d - mu * mu
        fpc = (d - r) / (d - 1)
        var = r * sigma_sq * fpc

        expected_var = 290 / 17
        assert abs(var - expected_var) < 1e-10, f"Var={var}, expected={expected_var}"

        # Also check E[HCP] = 10
        expected_hcp = r * mu
        assert abs(expected_hcp - 10.0) < 1e-10

    def test_wide_target_never_rejects(self):
        """Target 0-37 (full range): should never reject regardless of drawn HCP."""
        assert _check_hcp_feasibility(
            drawn_hcp=0, cards_remaining=13,
            deck_size=52, deck_hcp_sum=40, deck_hcp_sum_sq=120,
            target_min=0, target_max=37,
        ) is True
        assert _check_hcp_feasibility(
            drawn_hcp=20, cards_remaining=5,
            deck_size=30, deck_hcp_sum=15, deck_hcp_sum_sq=45,
            target_min=0, target_max=37,
        ) is True
