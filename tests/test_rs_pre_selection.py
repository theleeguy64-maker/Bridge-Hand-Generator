# tests/test_rs_pre_selection.py
"""
Tests for RS (Random Suit) pre-selection and RS-aware pre-allocation.

Organised by batch:
  B1 - _pre_select_rs_suits()
  B2 - _dispersion_check() with rs_pre_selections
  B3 - _pre_allocate_rs()
  B4 - _deal_with_help() with rs_pre_selections
"""

import random

import pytest

from bridge_engine import deal_generator as dg


# ===================================================================
# Dummy helpers (duck-typed, matching test_shape_help_v3.py pattern)
# ===================================================================


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


class _DummyRS:
    """Minimal duck-typed RandomSuitConstraintData for testing."""

    def __init__(self, allowed_suits, required_suits_count, suit_ranges=None,
                 pair_overrides=None):
        self.allowed_suits = allowed_suits
        self.required_suits_count = required_suits_count
        self.suit_ranges = suit_ranges or [_DummySuitRange(min_cards=6)]
        self.pair_overrides = pair_overrides or []


class _DummySubProfile:
    """Minimal duck-typed SubProfile for testing."""

    def __init__(self, s=0, h=0, d=0, c=0, rs=None):
        self.standard = _DummyStandard(s=s, h=h, d=d, c=c)
        self.random_suit_constraint = rs
        self.partner_contingent_constraint = None
        self.opponents_contingent_suit_constraint = None
        self.weight_percent = 100.0
        self.ns_role_usage = "any"


# ===================================================================
# B1 — _pre_select_rs_suits()
# ===================================================================


class TestPreSelectRsSuits:
    """Tests for _pre_select_rs_suits()."""

    def test_no_rs_seats_returns_empty(self):
        """Standard-only subprofiles produce an empty dict."""
        subs = {"W": _DummySubProfile(), "N": _DummySubProfile()}
        result = dg._pre_select_rs_suits(random.Random(42), subs)
        assert result == {}

    def test_single_rs_seat_present(self):
        """A seat with RS constraint appears in the result."""
        rs = _DummyRS(allowed_suits=["S", "H", "D"], required_suits_count=1)
        subs = {
            "W": _DummySubProfile(rs=rs),
            "N": _DummySubProfile(),
        }
        result = dg._pre_select_rs_suits(random.Random(42), subs)
        assert "W" in result
        assert "N" not in result

    def test_rs_count_1_yields_list_of_length_1(self):
        """required_suits_count=1 produces a single-element list."""
        rs = _DummyRS(allowed_suits=["S", "H", "D"], required_suits_count=1)
        subs = {"W": _DummySubProfile(rs=rs)}
        result = dg._pre_select_rs_suits(random.Random(42), subs)
        assert len(result["W"]) == 1

    def test_rs_count_2_yields_list_of_length_2(self):
        """required_suits_count=2 produces a two-element list."""
        rs = _DummyRS(
            allowed_suits=["S", "H", "D", "C"],
            required_suits_count=2,
            suit_ranges=[_DummySuitRange(min_cards=4), _DummySuitRange(min_cards=4)],
        )
        subs = {"N": _DummySubProfile(rs=rs)}
        result = dg._pre_select_rs_suits(random.Random(42), subs)
        assert len(result["N"]) == 2

    def test_chosen_suits_from_allowed(self):
        """Pre-selected suits must be drawn from allowed_suits."""
        rs = _DummyRS(allowed_suits=["S", "H"], required_suits_count=1)
        subs = {"W": _DummySubProfile(rs=rs)}
        for seed in range(50):
            result = dg._pre_select_rs_suits(random.Random(seed), subs)
            assert result["W"][0] in ("S", "H"), f"seed={seed}: {result['W']}"

    def test_deterministic_with_seed(self):
        """Same seed produces same result."""
        rs = _DummyRS(allowed_suits=["S", "H", "D"], required_suits_count=1)
        subs = {"W": _DummySubProfile(rs=rs)}
        r1 = dg._pre_select_rs_suits(random.Random(123), subs)
        r2 = dg._pre_select_rs_suits(random.Random(123), subs)
        assert r1 == r2

    def test_multiple_rs_seats_independent(self):
        """Multiple RS seats each get their own pre-selection."""
        rs_w = _DummyRS(allowed_suits=["S", "H", "D"], required_suits_count=1)
        rs_n = _DummyRS(allowed_suits=["S", "H", "D", "C"], required_suits_count=2,
                        suit_ranges=[_DummySuitRange(), _DummySuitRange()])
        subs = {
            "W": _DummySubProfile(rs=rs_w),
            "N": _DummySubProfile(rs=rs_n),
            "S": _DummySubProfile(),
            "E": _DummySubProfile(),
        }
        result = dg._pre_select_rs_suits(random.Random(42), subs)
        assert "W" in result and len(result["W"]) == 1
        assert "N" in result and len(result["N"]) == 2
        assert "S" not in result
        assert "E" not in result

    def test_empty_allowed_suits_skipped(self):
        """RS with empty allowed_suits is skipped."""
        rs = _DummyRS(allowed_suits=[], required_suits_count=1)
        subs = {"W": _DummySubProfile(rs=rs)}
        result = dg._pre_select_rs_suits(random.Random(42), subs)
        assert "W" not in result

    def test_required_count_exceeds_allowed_skipped(self):
        """RS with required_suits_count > len(allowed) is skipped."""
        rs = _DummyRS(allowed_suits=["S"], required_suits_count=2)
        subs = {"W": _DummySubProfile(rs=rs)}
        result = dg._pre_select_rs_suits(random.Random(42), subs)
        assert "W" not in result

    def test_required_count_zero_skipped(self):
        """RS with required_suits_count=0 is skipped."""
        rs = _DummyRS(allowed_suits=["S", "H"], required_suits_count=0)
        subs = {"W": _DummySubProfile(rs=rs)}
        result = dg._pre_select_rs_suits(random.Random(42), subs)
        assert "W" not in result


# ===================================================================
# B2 — _dispersion_check() with RS pre-selections
# ===================================================================


class _DummyPairOverride:
    """Minimal duck-typed SuitPairOverride for testing."""

    def __init__(self, suits, first_range, second_range):
        self.suits = suits
        self.first_range = first_range
        self.second_range = second_range


class TestDispersionCheckRS:
    """Tests for _dispersion_check() with rs_pre_selections param."""

    def test_backward_compat_no_rs(self):
        """Without rs_pre_selections, behaviour is unchanged."""
        subs = {"W": _DummySubProfile(s=6), "N": _DummySubProfile()}
        # Standard-only: W has 6 spades min → tight
        result = dg._dispersion_check(subs)
        assert "W" in result
        assert "N" not in result

    def test_backward_compat_none_rs(self):
        """Explicitly passing rs_pre_selections=None is same as omitting it."""
        subs = {"W": _DummySubProfile(s=6)}
        r1 = dg._dispersion_check(subs)
        r2 = dg._dispersion_check(subs, rs_pre_selections=None)
        assert r1 == r2

    def test_rs_seat_flagged_tight(self):
        """RS seat with min_cards=6 in pre-selected suit is flagged tight.

        This is the "Defense to Weak 2s" case: standard min_cards=0 everywhere,
        but RS says pick 1 of {S,H,D} with exactly 6 cards.
        """
        # Standard: all zeros.  RS: pick 1 of {S,H,D}, min_cards=6.
        rs = _DummyRS(
            allowed_suits=["S", "H", "D"],
            required_suits_count=1,
            suit_ranges=[_DummySuitRange(min_cards=6, max_cards=6)],
        )
        subs = {"W": _DummySubProfile(rs=rs)}
        # Without RS pre-selections: W is not tight (standard min_cards=0).
        assert "W" not in dg._dispersion_check(subs)
        # With RS pre-selections: W is tight (RS min_cards=6, P(>=6)≈6.3%).
        result = dg._dispersion_check(subs, rs_pre_selections={"W": ["H"]})
        assert "W" in result

    def test_rs_seat_loose_not_flagged(self):
        """RS seat with min_cards=3 is not flagged (P(>=3)≈49.7% > 19%)."""
        rs = _DummyRS(
            allowed_suits=["S", "H", "D"],
            required_suits_count=1,
            suit_ranges=[_DummySuitRange(min_cards=3, max_cards=13)],
        )
        subs = {"W": _DummySubProfile(rs=rs)}
        result = dg._dispersion_check(subs, rs_pre_selections={"W": ["S"]})
        assert "W" not in result

    def test_already_tight_from_standard_not_rechecked(self):
        """A seat already tight from standard constraints stays tight,
        even if RS is also present."""
        rs = _DummyRS(
            allowed_suits=["S", "H"],
            required_suits_count=1,
            suit_ranges=[_DummySuitRange(min_cards=6)],
        )
        # s=6 in standard makes W tight via standard path.
        subs = {"W": _DummySubProfile(s=6, rs=rs)}
        result = dg._dispersion_check(subs, rs_pre_selections={"W": ["H"]})
        assert "W" in result

    def test_rs_two_suits_pair_overrides(self):
        """2-suit RS with pair_overrides: uses override ranges for tightness."""
        first_range = _DummySuitRange(min_cards=5, max_cards=5)
        second_range = _DummySuitRange(min_cards=6, max_cards=6)
        override = _DummyPairOverride(
            suits=["S", "H"],
            first_range=first_range,
            second_range=second_range,
        )
        rs = _DummyRS(
            allowed_suits=["S", "H", "D"],
            required_suits_count=2,
            suit_ranges=[_DummySuitRange(min_cards=4), _DummySuitRange(min_cards=4)],
            pair_overrides=[override],
        )
        subs = {"N": _DummySubProfile(rs=rs)}
        # Pre-selected S+H matches the override → second_range has min_cards=6 → tight.
        result = dg._dispersion_check(subs, rs_pre_selections={"N": ["S", "H"]})
        assert "N" in result

    def test_rs_two_suits_no_override_uses_default_ranges(self):
        """2-suit RS without matching override uses default suit_ranges."""
        rs = _DummyRS(
            allowed_suits=["S", "H", "D"],
            required_suits_count=2,
            suit_ranges=[_DummySuitRange(min_cards=6), _DummySuitRange(min_cards=6)],
            pair_overrides=[],
        )
        subs = {"N": _DummySubProfile(rs=rs)}
        # Both ranges have min_cards=6 → tight.
        result = dg._dispersion_check(subs, rs_pre_selections={"N": ["S", "D"]})
        assert "N" in result

    def test_non_rs_seat_unaffected_by_rs_pre_selections(self):
        """A standard-only seat is not affected by rs_pre_selections dict."""
        subs = {"W": _DummySubProfile(), "N": _DummySubProfile()}
        result = dg._dispersion_check(
            subs, rs_pre_selections={"W": ["S"]}
        )
        # W has no RS constraint, so the pre-selection is harmless.
        assert "W" not in result
        assert "N" not in result


# ===================================================================
# B3 — _pre_allocate_rs()
# ===================================================================


def _make_deck():
    """Build a standard 52-card deck for testing."""
    ranks = "AKQJT98765432"
    suits = "SHDC"
    return [r + s for s in suits for r in ranks]


class TestPreAllocateRS:
    """Tests for _pre_allocate_rs()."""

    def test_single_suit_allocates_correct_count(self):
        """RS min_cards=6, fraction=0.75 → pre-allocate 4 cards."""
        rs = _DummyRS(
            allowed_suits=["S", "H", "D"],
            required_suits_count=1,
            suit_ranges=[_DummySuitRange(min_cards=6, max_cards=6)],
        )
        sub = _DummySubProfile(rs=rs)
        deck = _make_deck()
        pre = dg._pre_allocate_rs(random.Random(42), deck, sub, ["H"])
        assert len(pre) == 4  # floor(6 * 0.75) = 4

    def test_pre_allocated_cards_are_from_correct_suit(self):
        """All pre-allocated cards should be from the pre-selected suit."""
        rs = _DummyRS(
            allowed_suits=["S", "H", "D"],
            required_suits_count=1,
            suit_ranges=[_DummySuitRange(min_cards=6)],
        )
        sub = _DummySubProfile(rs=rs)
        deck = _make_deck()
        pre = dg._pre_allocate_rs(random.Random(42), deck, sub, ["D"])
        for card in pre:
            assert card[1] == "D", f"Expected diamond, got {card}"

    def test_deck_mutated(self):
        """Pre-allocated cards are removed from the deck."""
        rs = _DummyRS(
            allowed_suits=["S", "H", "D"],
            required_suits_count=1,
            suit_ranges=[_DummySuitRange(min_cards=6)],
        )
        sub = _DummySubProfile(rs=rs)
        deck = _make_deck()
        original_len = len(deck)
        pre = dg._pre_allocate_rs(random.Random(42), deck, sub, ["S"])
        assert len(deck) == original_len - len(pre)
        # Pre-allocated cards should not be in deck.
        for card in pre:
            assert card not in deck

    def test_no_rs_constraint_returns_empty(self):
        """Subprofile without RS returns empty list."""
        sub = _DummySubProfile()  # No RS
        deck = _make_deck()
        pre = dg._pre_allocate_rs(random.Random(42), deck, sub, ["S"])
        assert pre == []

    def test_min_cards_zero_returns_empty(self):
        """RS with min_cards=0 has nothing to pre-allocate."""
        rs = _DummyRS(
            allowed_suits=["S", "H"],
            required_suits_count=1,
            suit_ranges=[_DummySuitRange(min_cards=0)],
        )
        sub = _DummySubProfile(rs=rs)
        deck = _make_deck()
        pre = dg._pre_allocate_rs(random.Random(42), deck, sub, ["S"])
        assert pre == []

    def test_two_suits_allocates_both(self):
        """2-suit RS pre-allocates from both suits."""
        rs = _DummyRS(
            allowed_suits=["S", "H", "D"],
            required_suits_count=2,
            suit_ranges=[
                _DummySuitRange(min_cards=4, max_cards=6),
                _DummySuitRange(min_cards=4, max_cards=6),
            ],
        )
        sub = _DummySubProfile(rs=rs)
        deck = _make_deck()
        pre = dg._pre_allocate_rs(random.Random(42), deck, sub, ["S", "H"])
        # floor(4 * 0.75) = 3 per suit → 6 total
        assert len(pre) == 6
        s_cards = [c for c in pre if c[1] == "S"]
        h_cards = [c for c in pre if c[1] == "H"]
        assert len(s_cards) == 3
        assert len(h_cards) == 3

    def test_pair_overrides_used(self):
        """2-suit RS with matching pair_override uses override ranges."""
        first_range = _DummySuitRange(min_cards=5, max_cards=7)
        second_range = _DummySuitRange(min_cards=6, max_cards=8)
        override = _DummyPairOverride(
            suits=["S", "H"],
            first_range=first_range,
            second_range=second_range,
        )
        rs = _DummyRS(
            allowed_suits=["S", "H", "D"],
            required_suits_count=2,
            suit_ranges=[_DummySuitRange(min_cards=3), _DummySuitRange(min_cards=3)],
            pair_overrides=[override],
        )
        sub = _DummySubProfile(rs=rs)
        deck = _make_deck()
        pre = dg._pre_allocate_rs(random.Random(42), deck, sub, ["S", "H"])
        # Override: S gets floor(5*0.75)=3, H gets floor(6*0.75)=4 → 7 total
        assert len(pre) == 7

    def test_custom_fraction(self):
        """Custom fraction changes allocation count."""
        rs = _DummyRS(
            allowed_suits=["S", "H", "D"],
            required_suits_count=1,
            suit_ranges=[_DummySuitRange(min_cards=6)],
        )
        sub = _DummySubProfile(rs=rs)
        deck = _make_deck()
        pre = dg._pre_allocate_rs(random.Random(42), deck, sub, ["S"], fraction=0.75)
        # floor(6 * 0.75) = 4
        assert len(pre) == 4


# ===================================================================
# B4 — _deal_with_help() with rs_pre_selections
# ===================================================================


class TestDealWithHelpRS:
    """Tests for _deal_with_help() with RS pre-selections."""

    def test_backward_compat_no_rs(self):
        """Without rs_pre_selections, behaviour is unchanged."""
        # W tight (standard min 6 spades), N/S/E loose.
        subs = {
            "W": _DummySubProfile(s=6),
            "N": _DummySubProfile(),
            "S": _DummySubProfile(),
            "E": _DummySubProfile(),
        }
        tight = {"W"}
        order = ["W", "N", "S", "E"]
        deck = _make_deck()
        rng = random.Random(42)
        hands, rejected = dg._deal_with_help(rng, deck, subs, tight, order)
        assert rejected is None
        assert hands is not None
        for seat in "WNSE":
            assert len(hands[seat]) == 13

    def test_rs_seat_gets_rs_pre_allocation(self):
        """RS seat flagged tight gets cards pre-allocated from RS suit."""
        # W: standard all zeros, RS pick 1 of {S,H,D} with 6 cards.
        rs = _DummyRS(
            allowed_suits=["S", "H", "D"],
            required_suits_count=1,
            suit_ranges=[_DummySuitRange(min_cards=6, max_cards=6)],
        )
        subs = {
            "W": _DummySubProfile(rs=rs),
            "N": _DummySubProfile(),
            "S": _DummySubProfile(),
            "E": _DummySubProfile(),
        }
        tight = {"W"}  # Flagged by RS-aware dispersion check
        order = ["W", "N", "S", "E"]
        rs_pre = {"W": ["H"]}  # Pre-selected Hearts

        deck = _make_deck()
        rng = random.Random(42)
        hands, rejected = dg._deal_with_help(
            rng, deck, subs, tight, order, rs_pre_selections=rs_pre
        )
        assert rejected is None
        assert hands is not None
        # W should have 13 cards total.
        assert len(hands["W"]) == 13
        # W should have at least 3 hearts (the pre-allocated amount).
        hearts = [c for c in hands["W"] if c[1] == "H"]
        assert len(hearts) >= 3, f"W has {len(hearts)} hearts, expected >= 3"

    def test_all_hands_13_cards_with_rs(self):
        """All 4 hands have exactly 13 cards when RS pre-allocation is active."""
        rs = _DummyRS(
            allowed_suits=["S", "H", "D"],
            required_suits_count=1,
            suit_ranges=[_DummySuitRange(min_cards=6)],
        )
        subs = {
            "W": _DummySubProfile(rs=rs),
            "N": _DummySubProfile(),
            "S": _DummySubProfile(),
            "E": _DummySubProfile(),
        }
        tight = {"W"}
        order = ["W", "N", "S", "E"]
        rs_pre = {"W": ["D"]}

        deck = _make_deck()
        hands, _ = dg._deal_with_help(
            random.Random(42), deck, subs, tight, order, rs_pre_selections=rs_pre
        )
        assert hands is not None
        total_cards = sum(len(h) for h in hands.values())
        assert total_cards == 52
        for seat in "WNSE":
            assert len(hands[seat]) == 13, f"{seat} has {len(hands[seat])} cards"

    def test_no_duplicate_cards_with_rs(self):
        """No card appears in more than one hand with RS pre-allocation."""
        rs = _DummyRS(
            allowed_suits=["S", "H", "D"],
            required_suits_count=1,
            suit_ranges=[_DummySuitRange(min_cards=6)],
        )
        subs = {
            "W": _DummySubProfile(rs=rs),
            "N": _DummySubProfile(),
            "S": _DummySubProfile(),
            "E": _DummySubProfile(),
        }
        tight = {"W"}
        order = ["W", "N", "S", "E"]
        rs_pre = {"W": ["S"]}

        deck = _make_deck()
        hands, _ = dg._deal_with_help(
            random.Random(42), deck, subs, tight, order, rs_pre_selections=rs_pre
        )
        assert hands is not None
        all_cards = []
        for h in hands.values():
            all_cards.extend(h)
        assert len(set(all_cards)) == 52, "Duplicate cards found"

    def test_standard_plus_rs_combined_pre_allocation(self):
        """Seat with both standard minima and RS gets both pre-allocations."""
        # Standard: min 2 clubs.  RS: pick 1 of {S,H,D} with 6 cards.
        rs = _DummyRS(
            allowed_suits=["S", "H", "D"],
            required_suits_count=1,
            suit_ranges=[_DummySuitRange(min_cards=6)],
        )
        subs = {
            "W": _DummySubProfile(c=2, rs=rs),  # clubs=2 standard + RS
            "N": _DummySubProfile(),
            "S": _DummySubProfile(),
            "E": _DummySubProfile(),
        }
        tight = {"W"}
        order = ["W", "N", "S", "E"]
        rs_pre = {"W": ["H"]}

        deck = _make_deck()
        hands, _ = dg._deal_with_help(
            random.Random(42), deck, subs, tight, order, rs_pre_selections=rs_pre
        )
        assert hands is not None
        assert len(hands["W"]) == 13
        # W should have clubs from standard pre-alloc + hearts from RS pre-alloc.
        clubs = [c for c in hands["W"] if c[1] == "C"]
        hearts = [c for c in hands["W"] if c[1] == "H"]
        # Standard pre-alloc: floor(2*0.5)=1 club.  RS: floor(6*0.5)=3 hearts.
        # Then random fill may add more.
        assert len(clubs) >= 1, f"W has {len(clubs)} clubs, expected >= 1"
        assert len(hearts) >= 3, f"W has {len(hearts)} hearts, expected >= 3"

    def test_rs_pre_selection_for_non_tight_seat_ignored(self):
        """RS pre-selection for a seat NOT in tight_seats is ignored."""
        rs = _DummyRS(
            allowed_suits=["S", "H", "D"],
            required_suits_count=1,
            suit_ranges=[_DummySuitRange(min_cards=6)],
        )
        subs = {
            "W": _DummySubProfile(rs=rs),
            "N": _DummySubProfile(),
            "S": _DummySubProfile(),
            "E": _DummySubProfile(),
        }
        tight = set()  # W not flagged as tight
        order = ["W", "N", "S", "E"]
        rs_pre = {"W": ["H"]}

        deck = _make_deck()
        hands, _ = dg._deal_with_help(
            random.Random(42), deck, subs, tight, order, rs_pre_selections=rs_pre
        )
        assert hands is not None
        # W gets 13 random cards, no guaranteed pre-allocation.
        assert len(hands["W"]) == 13
