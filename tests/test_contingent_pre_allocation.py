# tests/test_contingent_pre_allocation.py
"""
Tests for OC/PC contingent pre-allocation and related helpers.

Covers:
  - _resolve_contingent_target_suit() — target suit resolution
  - _pre_allocate_contingent() — card pre-allocation with HCP targeting
  - _dispersion_check() OC/PC extension — tightness flagging
  - _pair_jointly_viable() HCP check — combined HCP minimum validation
"""

from __future__ import annotations

import random
from types import SimpleNamespace

import pytest

from bridge_engine import deal_generator_v2 as dg
from bridge_engine.deal_generator_helpers import _build_deck
from bridge_engine.deal_generator_types import _CARD_HCP
from bridge_engine.profile_viability import _pair_jointly_viable


# ---------------------------------------------------------------------------
# Helpers: lightweight duck-typed stubs
# ---------------------------------------------------------------------------


class _DummySuitRange:
    """Minimal duck-typed SuitRange for testing."""

    def __init__(self, min_cards=0, max_cards=13, min_hcp=0, max_hcp=10):
        self.min_cards = min_cards
        self.max_cards = max_cards
        self.min_hcp = min_hcp
        self.max_hcp = max_hcp


class _DummyStandard:
    """Minimal duck-typed StandardSuitConstraints for testing."""

    def __init__(self, s=0, h=0, d=0, c=0):
        self.spades = _DummySuitRange(min_cards=s)
        self.hearts = _DummySuitRange(min_cards=h)
        self.diamonds = _DummySuitRange(min_cards=d)
        self.clubs = _DummySuitRange(min_cards=c)
        self.total_min_hcp = 0
        self.total_max_hcp = 37


class _DummyOC:
    """Minimal duck-typed OpponentsContingentSuitConstraintData."""

    def __init__(self, opponent_seat="W", suit_range=None, use_non_chosen_suit=False):
        self.opponent_seat = opponent_seat
        self.suit_range = suit_range or _DummySuitRange()
        self.use_non_chosen_suit = use_non_chosen_suit


class _DummyPC:
    """Minimal duck-typed PartnerContingentConstraintData."""

    def __init__(self, partner_seat="S", suit_range=None, use_non_chosen_suit=False):
        self.partner_seat = partner_seat
        self.suit_range = suit_range or _DummySuitRange()
        self.use_non_chosen_suit = use_non_chosen_suit


class _DummySubProfile:
    """Minimal duck-typed SubProfile with OC/PC support."""

    def __init__(self, s=0, h=0, d=0, c=0, oc=None, pc=None):
        self.standard = _DummyStandard(s=s, h=h, d=d, c=c)
        self.random_suit_constraint = None
        self.partner_contingent_constraint = pc
        self.opponents_contingent_suit_constraint = oc
        self.weight_percent = 100.0
        self.ns_role_usage = "any"


def _toy_sub(min_hcp=0, max_hcp=37):
    """Toy subprofile for _pair_jointly_viable tests."""
    return SimpleNamespace(
        min_hcp=min_hcp,
        max_hcp=max_hcp,
        min_suit_counts={},
        max_suit_counts={},
        standard=None,
    )


# ===================================================================
# _resolve_contingent_target_suit()
# ===================================================================


class TestResolveContingentTargetSuit:
    """Tests for _resolve_contingent_target_suit()."""

    def test_returns_chosen_suit(self):
        """When use_non_chosen=False, returns first RS-chosen suit."""
        rs_pre = {"W": ["H"]}
        result = dg._resolve_contingent_target_suit("W", False, rs_pre)
        assert result == "H"

    def test_returns_first_chosen_when_multiple(self):
        """When opponent chose 2 suits, returns the first one."""
        rs_pre = {"W": ["S", "D"]}
        result = dg._resolve_contingent_target_suit("W", False, rs_pre)
        assert result == "S"

    def test_returns_none_when_seat_has_no_pre_selection(self):
        """When referenced seat has no RS pre-selection, returns None."""
        rs_pre = {"E": ["H"]}
        result = dg._resolve_contingent_target_suit("W", False, rs_pre)
        assert result is None

    def test_returns_none_when_pre_selections_empty(self):
        """When rs_pre_selections is empty dict, returns None."""
        result = dg._resolve_contingent_target_suit("W", False, {})
        assert result is None

    def test_non_chosen_suit_returns_complement(self):
        """When use_non_chosen=True, returns a suit NOT chosen by opponent."""
        rs_pre = {"W": ["H"]}
        rs_allowed = {"W": ["S", "H"]}
        result = dg._resolve_contingent_target_suit("W", True, rs_pre, rs_allowed)
        assert result == "S"

    def test_non_chosen_multiple_returns_first(self):
        """With multiple non-chosen suits, returns the first one."""
        rs_pre = {"W": ["H"]}
        rs_allowed = {"W": ["S", "H", "D", "C"]}
        result = dg._resolve_contingent_target_suit("W", True, rs_pre, rs_allowed)
        assert result == "S"

    def test_non_chosen_all_chosen_returns_none(self):
        """When opponent chose ALL allowed suits, no non-chosen → None."""
        rs_pre = {"W": ["S", "H"]}
        rs_allowed = {"W": ["S", "H"]}
        result = dg._resolve_contingent_target_suit("W", True, rs_pre, rs_allowed)
        assert result is None

    def test_non_chosen_no_allowed_suits_returns_none(self):
        """When rs_allowed_suits is None, non-chosen path returns None."""
        rs_pre = {"W": ["H"]}
        result = dg._resolve_contingent_target_suit("W", True, rs_pre, None)
        assert result is None

    def test_non_chosen_seat_not_in_allowed_returns_none(self):
        """When referenced seat not in rs_allowed_suits, returns None."""
        rs_pre = {"W": ["H"]}
        rs_allowed = {"E": ["S", "H"]}
        result = dg._resolve_contingent_target_suit("W", True, rs_pre, rs_allowed)
        assert result is None


# ===================================================================
# _pre_allocate_contingent()
# ===================================================================


class TestPreAllocateContingent:
    """Tests for _pre_allocate_contingent()."""

    def test_allocates_min_cards_from_deck(self):
        """Should pre-allocate min_cards cards of the target suit."""
        rng = random.Random(42)
        deck = _build_deck()
        sr = _DummySuitRange(min_cards=3, max_cards=6, min_hcp=0, max_hcp=10)
        result = dg._pre_allocate_contingent(rng, deck, "S", sr)
        assert len(result) == 3
        assert all(c[1] == "S" for c in result)

    def test_cards_removed_from_deck(self):
        """Pre-allocated cards should be removed from the deck."""
        rng = random.Random(42)
        deck = _build_deck()
        original_len = len(deck)
        sr = _DummySuitRange(min_cards=4, max_cards=6, min_hcp=0, max_hcp=10)
        result = dg._pre_allocate_contingent(rng, deck, "H", sr)
        assert len(deck) == original_len - len(result)
        # None of the pre-allocated cards should remain in deck.
        for card in result:
            assert card not in deck

    def test_skips_when_min_cards_zero(self):
        """Should return empty list when min_cards=0 (shortness constraint)."""
        rng = random.Random(42)
        deck = _build_deck()
        sr = _DummySuitRange(min_cards=0, max_cards=1, min_hcp=0, max_hcp=2)
        result = dg._pre_allocate_contingent(rng, deck, "D", sr)
        assert result == []
        assert len(deck) == 52  # Deck unchanged

    def test_returns_empty_when_no_cards_of_suit(self):
        """Should return empty list when deck has no cards of target suit."""
        rng = random.Random(42)
        # Build a deck with no spades.
        deck = [c for c in _build_deck() if c[1] != "S"]
        sr = _DummySuitRange(min_cards=3, max_cards=6, min_hcp=0, max_hcp=10)
        result = dg._pre_allocate_contingent(rng, deck, "S", sr)
        assert result == []

    def test_caps_at_available_cards(self):
        """When fewer cards available than min_cards, takes what's there."""
        rng = random.Random(42)
        # Build a deck with only 2 clubs.
        deck = [c for c in _build_deck() if c[1] == "C"][:2]
        sr = _DummySuitRange(min_cards=5, max_cards=8, min_hcp=0, max_hcp=10)
        result = dg._pre_allocate_contingent(rng, deck, "C", sr)
        assert len(result) == 2

    def test_hcp_targeting_respects_range(self):
        """Over many runs, HCP targeting should produce values in range."""
        # Use a tight HCP range so we can verify targeting works.
        sr = _DummySuitRange(min_cards=5, max_cards=8, min_hcp=5, max_hcp=7)
        in_range_count = 0
        trials = 100
        for seed in range(trials):
            rng = random.Random(seed)
            deck = _build_deck()
            rng.shuffle(deck)
            result = dg._pre_allocate_contingent(rng, deck, "H", sr)
            if not result:
                continue
            hcp = sum(_CARD_HCP[c] for c in result)
            # Pro-rated target for 5 cards from 5 min_cards:
            # target_low = floor(5 * 5 / 5) = 5
            # target_high = ceil(7 * 5 / 5) = 7
            if 5 <= hcp <= 7:
                in_range_count += 1
        # With rejection sampling, we expect a high hit rate (>60%).
        assert in_range_count > 50, f"Only {in_range_count}/{trials} trials hit HCP target 5-7"

    def test_all_cards_are_from_target_suit(self):
        """Every pre-allocated card must be from the target suit."""
        for suit in ("S", "H", "D", "C"):
            rng = random.Random(99)
            deck = _build_deck()
            rng.shuffle(deck)
            sr = _DummySuitRange(min_cards=4, max_cards=8, min_hcp=0, max_hcp=10)
            result = dg._pre_allocate_contingent(rng, deck, suit, sr)
            assert all(c[1] == suit for c in result), f"Found non-{suit} card in pre-allocation"


# ===================================================================
# _dispersion_check() — OC/PC extension
# ===================================================================


class TestDispersionCheckContingent:
    """Tests for OC/PC tightness flagging in _dispersion_check()."""

    def test_oc_tight_seat_flagged(self):
        """OC seat with high min_cards should be flagged tight."""
        oc = _DummyOC(
            opponent_seat="W",
            suit_range=_DummySuitRange(min_cards=5),  # P(>=5) = 0.189
        )
        subs = {
            "N": _DummySubProfile(oc=oc),
            "E": _DummySubProfile(),
            "S": _DummySubProfile(),
            "W": _DummySubProfile(),
        }
        rs_pre = {"W": ["H"]}  # W has RS pre-selection
        result = dg._dispersion_check(subs, rs_pre_selections=rs_pre)
        assert "N" in result

    def test_oc_loose_seat_not_flagged(self):
        """OC seat with low min_cards should NOT be flagged tight."""
        oc = _DummyOC(
            opponent_seat="W",
            suit_range=_DummySuitRange(min_cards=2),  # P(>=2) = 0.965
        )
        subs = {
            "N": _DummySubProfile(oc=oc),
            "E": _DummySubProfile(),
            "S": _DummySubProfile(),
            "W": _DummySubProfile(),
        }
        rs_pre = {"W": ["H"]}
        result = dg._dispersion_check(subs, rs_pre_selections=rs_pre)
        assert "N" not in result

    def test_oc_zero_min_cards_not_flagged(self):
        """OC seat with min_cards=0 (shortness) should NOT be flagged."""
        oc = _DummyOC(
            opponent_seat="W",
            suit_range=_DummySuitRange(min_cards=0),
        )
        subs = {
            "N": _DummySubProfile(oc=oc),
            "E": _DummySubProfile(),
            "S": _DummySubProfile(),
            "W": _DummySubProfile(),
        }
        rs_pre = {"W": ["S"]}
        result = dg._dispersion_check(subs, rs_pre_selections=rs_pre)
        assert "N" not in result

    def test_oc_no_rs_pre_selection_not_flagged(self):
        """OC seat should NOT be flagged if referenced seat has no RS pre-selection."""
        oc = _DummyOC(
            opponent_seat="W",
            suit_range=_DummySuitRange(min_cards=6),
        )
        subs = {
            "N": _DummySubProfile(oc=oc),
            "E": _DummySubProfile(),
            "S": _DummySubProfile(),
            "W": _DummySubProfile(),
        }
        rs_pre = {"E": ["H"]}  # W has no RS — only E does
        result = dg._dispersion_check(subs, rs_pre_selections=rs_pre)
        assert "N" not in result

    def test_pc_tight_seat_flagged(self):
        """PC seat with high min_cards should be flagged tight."""
        pc = _DummyPC(
            partner_seat="S",
            suit_range=_DummySuitRange(min_cards=5),
        )
        subs = {
            "N": _DummySubProfile(pc=pc),
            "E": _DummySubProfile(),
            "S": _DummySubProfile(),
            "W": _DummySubProfile(),
        }
        rs_pre = {"S": ["D"]}  # Partner S has RS pre-selection
        result = dg._dispersion_check(subs, rs_pre_selections=rs_pre)
        assert "N" in result

    def test_already_tight_from_standard_not_rechecked(self):
        """Seat already flagged tight by standard constraints skips OC check."""
        oc = _DummyOC(
            opponent_seat="W",
            suit_range=_DummySuitRange(min_cards=6),
        )
        # N has 6 spades (tight from standard) + OC constraint.
        subs = {
            "N": _DummySubProfile(s=6, oc=oc),
            "E": _DummySubProfile(),
            "S": _DummySubProfile(),
            "W": _DummySubProfile(),
        }
        rs_pre = {"W": ["H"]}
        result = dg._dispersion_check(subs, rs_pre_selections=rs_pre)
        # N should be flagged (from standard), but only once.
        assert "N" in result

    def test_no_rs_pre_selections_skips_oc_pc_check(self):
        """When rs_pre_selections is None, OC/PC block is skipped entirely."""
        oc = _DummyOC(
            opponent_seat="W",
            suit_range=_DummySuitRange(min_cards=6),
        )
        subs = {
            "N": _DummySubProfile(oc=oc),
            "E": _DummySubProfile(),
            "S": _DummySubProfile(),
            "W": _DummySubProfile(),
        }
        # No rs_pre_selections at all.
        result = dg._dispersion_check(subs, rs_pre_selections=None)
        assert "N" not in result


# ===================================================================
# _pair_jointly_viable() — HCP check
# ===================================================================


class TestPairJointlyViableHcp:
    """Tests for the combined HCP minimum check in _pair_jointly_viable()."""

    def test_combined_hcp_over_40_returns_false(self):
        """Two seats with combined min_hcp > 40 should fail viability."""
        n = _toy_sub(min_hcp=22)
        s = _toy_sub(min_hcp=20)
        assert _pair_jointly_viable(n, s) is False

    def test_combined_hcp_exactly_40_passes(self):
        """Combined min_hcp = 40 (edge case) should pass."""
        n = _toy_sub(min_hcp=20)
        s = _toy_sub(min_hcp=20)
        assert _pair_jointly_viable(n, s) is True

    def test_combined_hcp_under_40_passes(self):
        """Combined min_hcp < 40 should pass."""
        n = _toy_sub(min_hcp=10)
        s = _toy_sub(min_hcp=15)
        assert _pair_jointly_viable(n, s) is True

    def test_one_seat_zero_hcp_always_passes(self):
        """If one seat has min_hcp=0, combined can never exceed 37."""
        n = _toy_sub(min_hcp=0)
        s = _toy_sub(min_hcp=37)
        assert _pair_jointly_viable(n, s) is True

    def test_combined_hcp_41_fails(self):
        """Combined min_hcp = 41 — just over limit — should fail."""
        n = _toy_sub(min_hcp=21)
        s = _toy_sub(min_hcp=20)
        assert _pair_jointly_viable(n, s) is False
