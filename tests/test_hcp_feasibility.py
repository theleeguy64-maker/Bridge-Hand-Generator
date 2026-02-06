# tests/test_hcp_feasibility.py
"""
Unit tests and integration tests for HCP feasibility utilities (TODO #5).

Part 1 (unit tests): Call the functions directly — no dependency on
  ENABLE_HCP_FEASIBILITY_CHECK gate flag.  Prove the math works.

Part 2 (integration tests): Monkeypatch the gate to True and verify that
  _deal_with_help correctly rejects infeasible hands and passes feasible ones.
  Uses real StandardSuitConstraints / SubProfile dataclasses (not dummies).
"""
from __future__ import annotations

import math
import random
import pytest

import bridge_engine.deal_generator as dg
from bridge_engine.deal_generator import (
    _card_hcp,
    _deck_hcp_stats,
    _check_hcp_feasibility,
    _build_deck,
)
from bridge_engine.hand_profile import (
    StandardSuitConstraints,
    SubProfile,
    SuitRange,
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


# ---------------------------------------------------------------------------
# Integration tests: _deal_with_help with HCP feasibility gate
#
# These tests activate ENABLE_HCP_FEASIBILITY_CHECK via monkeypatch and
# verify that _deal_with_help correctly rejects or accepts hands based on
# HCP feasibility after pre-allocation.  Uses real dataclass types
# (StandardSuitConstraints, SubProfile, SuitRange) — not test dummies —
# because the gated code reads std.total_min_hcp / std.total_max_hcp.
# ---------------------------------------------------------------------------


def _open_suit_range() -> SuitRange:
    """Fully open suit range (0-13 cards, 0-37 HCP)."""
    return SuitRange()


def _open_standard(total_min: int = 0, total_max: int = 37) -> StandardSuitConstraints:
    """Open standard constraints with configurable total HCP."""
    sr = _open_suit_range()
    return StandardSuitConstraints(
        spades=sr, hearts=sr, diamonds=sr, clubs=sr,
        total_min_hcp=total_min, total_max_hcp=total_max,
    )


def _open_subprofile(total_min: int = 0, total_max: int = 37) -> SubProfile:
    """Open subprofile with configurable total HCP."""
    return SubProfile(standard=_open_standard(total_min, total_max))


def _tight_spades_subprofile(
    min_spades: int = 6,
    total_min: int = 0,
    total_max: int = 37,
) -> SubProfile:
    """Subprofile with tight spade constraint and configurable total HCP."""
    return SubProfile(
        standard=StandardSuitConstraints(
            spades=SuitRange(min_cards=min_spades, max_cards=13),
            hearts=SuitRange(),
            diamonds=SuitRange(),
            clubs=SuitRange(),
            total_min_hcp=total_min,
            total_max_hcp=total_max,
        )
    )


DEALING_ORDER = ["N", "E", "S", "W"]


class TestDealWithHelpHcpGate:
    """Integration tests for HCP feasibility check in _deal_with_help.

    These tests monkeypatch ENABLE_HCP_FEASIBILITY_CHECK to True and verify
    that the gated check correctly rejects infeasible hands and passes
    feasible ones.  Uses real dataclass types (not test dummies).
    """

    # -- Rejection cases (gate ON, impossible HCP) --

    def test_gate_on_rejects_impossible_low_hcp(self, monkeypatch):
        """North needs 6+ spades but only 0-2 total HCP — impossible.

        Pre-alloc gives 3 spades (50% of 6).  Even if all are spot cards
        (0 HCP drawn), the expected additional HCP from 10 random cards
        is ~8.2, giving ExpDown ≈ 4.4 > 2 = target_max.  Rejection fires
        regardless of which spade cards are picked.
        """
        monkeypatch.setattr(dg, "ENABLE_HCP_FEASIBILITY_CHECK", True)

        sub_n = _tight_spades_subprofile(min_spades=6, total_min=0, total_max=2)
        sub_open = _open_subprofile()
        subs = {"N": sub_n, "E": sub_open, "S": sub_open, "W": sub_open}

        # Try several seeds — all should reject North.
        for seed in [42, 99, 123, 777, 2024]:
            rng = random.Random(seed)
            deck = dg._build_deck()
            hands, rejected = dg._deal_with_help(
                rng, deck, subs, {"N"}, DEALING_ORDER
            )
            assert hands is None, f"seed={seed}: expected rejection but got hands"
            assert rejected == "N", f"seed={seed}: expected N rejected, got {rejected}"

    def test_gate_on_rejects_impossible_high_hcp(self, monkeypatch):
        """North needs 6+ spades and 35-37 total HCP — impossible.

        Pre-alloc gives at most 9 HCP (AS+KS+QS).  Expected additional from
        10 random cards is ~6-8.  ExpUp ≈ 12-19, well below target_min=35.
        Always rejected (too low to reach 35).
        """
        monkeypatch.setattr(dg, "ENABLE_HCP_FEASIBILITY_CHECK", True)

        sub_n = _tight_spades_subprofile(min_spades=6, total_min=35, total_max=37)
        sub_open = _open_subprofile()
        subs = {"N": sub_n, "E": sub_open, "S": sub_open, "W": sub_open}

        for seed in [42, 99, 123]:
            rng = random.Random(seed)
            deck = dg._build_deck()
            hands, rejected = dg._deal_with_help(
                rng, deck, subs, {"N"}, DEALING_ORDER
            )
            assert hands is None, f"seed={seed}: expected rejection"
            assert rejected == "N", f"seed={seed}: expected N rejected"

    def test_gate_on_first_tight_seat_rejected_stops_early(self, monkeypatch):
        """Multiple tight seats: rejection at first infeasible seat aborts deal.

        North is first in dealing order with impossible HCP.  South is also
        tight with impossible HCP but never gets checked because North's
        rejection aborts the deal early.
        """
        monkeypatch.setattr(dg, "ENABLE_HCP_FEASIBILITY_CHECK", True)

        sub_impossible = _tight_spades_subprofile(
            min_spades=6, total_min=0, total_max=2,
        )
        sub_open = _open_subprofile()
        subs = {
            "N": sub_impossible,
            "E": sub_open,
            "S": sub_impossible,   # Also impossible, but never reached
            "W": sub_open,
        }

        rng = random.Random(42)
        deck = dg._build_deck()
        hands, rejected = dg._deal_with_help(
            rng, deck, subs, {"N", "S"}, DEALING_ORDER
        )
        assert hands is None
        assert rejected == "N"  # North is first in dealing order

    # -- Feasible cases (gate ON, reachable HCP) --

    def test_gate_on_passes_feasible_wide_hcp(self, monkeypatch):
        """North needs 6+ spades, 0-37 HCP — always feasible.

        The full 0-37 range encompasses all possible HCP outcomes.
        No pre-allocation can make the hand infeasible.
        """
        monkeypatch.setattr(dg, "ENABLE_HCP_FEASIBILITY_CHECK", True)

        sub_n = _tight_spades_subprofile(min_spades=6, total_min=0, total_max=37)
        sub_open = _open_subprofile()
        subs = {"N": sub_n, "E": sub_open, "S": sub_open, "W": sub_open}

        for seed in [42, 99, 123]:
            rng = random.Random(seed)
            deck = dg._build_deck()
            hands, rejected = dg._deal_with_help(
                rng, deck, subs, {"N"}, DEALING_ORDER
            )
            assert hands is not None, f"seed={seed}: should not reject"
            assert rejected is None, f"seed={seed}: should not have rejected seat"
            assert len(hands["N"]) == 13

    def test_gate_on_passes_feasible_moderate_hcp(self, monkeypatch):
        """North needs 6+ spades, 5-20 HCP — well within expected range.

        Expected total HCP ~8-16 after pre-alloc + fill.  The 5-20 target
        comfortably overlaps with the 1-SD confidence interval in all cases.
        """
        monkeypatch.setattr(dg, "ENABLE_HCP_FEASIBILITY_CHECK", True)

        sub_n = _tight_spades_subprofile(min_spades=6, total_min=5, total_max=20)
        sub_open = _open_subprofile()
        subs = {"N": sub_n, "E": sub_open, "S": sub_open, "W": sub_open}

        for seed in [42, 99, 123]:
            rng = random.Random(seed)
            deck = dg._build_deck()
            hands, rejected = dg._deal_with_help(
                rng, deck, subs, {"N"}, DEALING_ORDER
            )
            assert hands is not None, f"seed={seed}: should not reject"
            assert rejected is None

    # -- Gate OFF: no rejection regardless --

    def test_gate_off_no_rejection_even_for_impossible(self, monkeypatch):
        """Gate OFF: impossible HCP proceeds without rejection.

        Same impossible scenario as test_gate_on_rejects_impossible_low_hcp,
        but with the gate explicitly set to False.  _deal_with_help should
        return hands normally — the HCP check never runs.
        """
        monkeypatch.setattr(dg, "ENABLE_HCP_FEASIBILITY_CHECK", False)

        sub_n = _tight_spades_subprofile(min_spades=6, total_min=0, total_max=2)
        sub_open = _open_subprofile()
        subs = {"N": sub_n, "E": sub_open, "S": sub_open, "W": sub_open}

        rng = random.Random(42)
        deck = dg._build_deck()
        hands, rejected = dg._deal_with_help(
            rng, deck, subs, {"N"}, DEALING_ORDER
        )
        assert hands is not None, "Gate OFF should not reject"
        assert rejected is None
        assert len(hands["N"]) == 13

    # -- Edge cases: when HCP check is skipped --

    def test_gate_on_non_tight_seats_not_checked(self, monkeypatch):
        """Gate ON but no tight seats — HCP check never activates.

        Non-tight seats skip pre-allocation entirely, so the HCP check
        (which runs after pre-alloc) never fires.
        """
        monkeypatch.setattr(dg, "ENABLE_HCP_FEASIBILITY_CHECK", True)

        # Impossible HCP (0-2) but NOT tight — no pre-alloc, no check.
        sub = _open_subprofile(total_min=0, total_max=2)
        subs = {"N": sub, "E": sub, "S": sub, "W": sub}

        rng = random.Random(42)
        deck = dg._build_deck()
        hands, rejected = dg._deal_with_help(
            rng, deck, subs, set(), DEALING_ORDER  # Empty tight_seats
        )
        assert hands is not None, "Non-tight seats should not trigger HCP check"
        assert rejected is None

    def test_gate_on_tight_seat_empty_prealloc_skips_check(self, monkeypatch):
        """Tight seat where pre-allocation returns empty skips HCP check.

        min_spades=1 → pre-alloc = floor(1 × 0.5) = 0 cards → empty list.
        The HCP check only fires when pre is non-empty, so it's skipped.
        """
        monkeypatch.setattr(dg, "ENABLE_HCP_FEASIBILITY_CHECK", True)

        # min_spades=1: pre-alloc = floor(0.5) = 0 → empty.
        sub_n = _tight_spades_subprofile(min_spades=1, total_min=0, total_max=2)
        sub_open = _open_subprofile()
        subs = {"N": sub_n, "E": sub_open, "S": sub_open, "W": sub_open}

        rng = random.Random(42)
        deck = dg._build_deck()
        hands, rejected = dg._deal_with_help(
            rng, deck, subs, {"N"}, DEALING_ORDER
        )
        # Pre-alloc is empty → HCP check skipped → hands returned.
        assert hands is not None, "Empty pre-alloc should skip HCP check"
        assert rejected is None

    def test_gate_on_last_seat_also_checked(self, monkeypatch):
        """Last seat in dealing order also gets pre-allocation and HCP check.

        West is last in dealing order.  With Phase-1 pre-allocation
        (restructured _deal_with_help), ALL tight seats — including the
        last — get pre-allocation.  The HCP check fires on the pre-allocated
        cards, and with impossible HCP (0-2 total with 6+ spades) it rejects.
        """
        monkeypatch.setattr(dg, "ENABLE_HCP_FEASIBILITY_CHECK", True)

        # W is last with impossible HCP — now gets pre-allocated and checked.
        sub_impossible = _tight_spades_subprofile(
            min_spades=6, total_min=0, total_max=2,
        )
        sub_open = _open_subprofile()
        subs = {
            "N": sub_open, "E": sub_open, "S": sub_open,
            "W": sub_impossible,
        }

        rng = random.Random(42)
        deck = dg._build_deck()
        hands, rejected = dg._deal_with_help(
            rng, deck, subs, {"W"}, DEALING_ORDER
        )
        # W is last but still gets pre-allocation + HCP check (Phase 1).
        # With impossible HCP (0-2) and 6 spades pre-allocated, rejection fires.
        assert hands is None
        assert rejected == "W"

    def test_gate_on_deck_integrity_after_rejection(self, monkeypatch):
        """After early HCP rejection, deck is partially consumed (not empty).

        When rejection fires, pre-allocated cards have been removed from the
        deck but no further dealing happens.  Verify the deck still has cards.
        """
        monkeypatch.setattr(dg, "ENABLE_HCP_FEASIBILITY_CHECK", True)

        sub_n = _tight_spades_subprofile(min_spades=6, total_min=0, total_max=2)
        sub_open = _open_subprofile()
        subs = {"N": sub_n, "E": sub_open, "S": sub_open, "W": sub_open}

        rng = random.Random(42)
        deck = dg._build_deck()
        original_size = len(deck)

        hands, rejected = dg._deal_with_help(
            rng, deck, subs, {"N"}, DEALING_ORDER
        )
        assert rejected == "N"
        # Pre-alloc removed 3 spades from the deck (floor(6*0.5)=3).
        # Deck should have 49 cards remaining (52 - 3 pre-allocated).
        assert len(deck) == original_size - 3
