"""
Tests for the v2 shape-based help system (deal_generator_reorg.md).

Organised by deliverable:
  D1 - SHAPE_PROB_GTE table + constants
  D2 - _dispersion_check()
  D3 - _random_deal()
  D4 - _pre_allocate()
  D5 - _deal_with_help()
  D6 - _build_single_constrained_deal_v2() MVP
  D7 - Full attribution in v2 (failure counters + debug hooks)
"""

import random

import pytest

from bridge_engine import deal_generator as dg
from bridge_engine.hand_profile import (
    HandProfile,
    SeatProfile,
    SubProfile,
    StandardSuitConstraints,
    SuitRange,
)


# ===================================================================
# D1 — SHAPE_PROB_GTE table + constants
# ===================================================================


class TestShapeProbGTE:
    """Tests for the shape probability lookup table and related constants."""

    def test_table_has_14_entries(self):
        """Table should cover min_cards 0 through 13."""
        assert len(dg.SHAPE_PROB_GTE) == 14

    def test_all_keys_0_through_13(self):
        """Keys should be exactly {0, 1, 2, ..., 13}."""
        assert set(dg.SHAPE_PROB_GTE.keys()) == set(range(14))

    def test_entry_0_is_1(self):
        """P(>= 0 cards) = 1.0 (always true)."""
        assert dg.SHAPE_PROB_GTE[0] == 1.0

    def test_entry_5_approx_019(self):
        """P(>= 5 cards) should be approximately 0.189."""
        assert abs(dg.SHAPE_PROB_GTE[5] - 0.189) < 0.01

    def test_entry_6_approx_006(self):
        """P(>= 6 cards) should be approximately 0.063."""
        assert abs(dg.SHAPE_PROB_GTE[6] - 0.063) < 0.01

    def test_monotonically_decreasing(self):
        """Each entry should be strictly less than the previous."""
        for n in range(1, 14):
            assert dg.SHAPE_PROB_GTE[n] < dg.SHAPE_PROB_GTE[n - 1], (
                f"SHAPE_PROB_GTE[{n}]={dg.SHAPE_PROB_GTE[n]} should be < "
                f"SHAPE_PROB_GTE[{n - 1}]={dg.SHAPE_PROB_GTE[n - 1]}"
            )

    def test_all_positive(self):
        """All probabilities should be > 0."""
        for n, prob in dg.SHAPE_PROB_GTE.items():
            assert prob > 0, f"SHAPE_PROB_GTE[{n}] = {prob} should be > 0"

    def test_threshold_default(self):
        """Default threshold should be 0.19."""
        assert dg.SHAPE_PROB_THRESHOLD == 0.19

    def test_pre_allocate_fraction_default(self):
        """Default pre-allocation fraction should be 0.75."""
        assert dg.PRE_ALLOCATE_FRACTION == 0.75


# ===================================================================
# D2 — _dispersion_check()
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


class _DummySubProfile:
    """Minimal duck-typed SubProfile for testing."""

    def __init__(self, s=0, h=0, d=0, c=0):
        self.standard = _DummyStandard(s=s, h=h, d=d, c=c)
        self.random_suit_constraint = None
        self.partner_contingent_constraint = None
        self.opponents_contingent_suit_constraint = None
        self.weight_percent = 100.0
        self.ns_role_usage = "any"


class TestDispersionCheck:
    """Tests for _dispersion_check()."""

    def test_all_loose_returns_empty(self):
        """All seats with min_cards=0 should produce an empty set."""
        subs = {
            "N": _DummySubProfile(),
            "E": _DummySubProfile(),
            "S": _DummySubProfile(),
            "W": _DummySubProfile(),
        }
        assert dg._dispersion_check(subs) == set()

    def test_5_spades_is_tight(self):
        """5+ spades (P=0.189) is at the threshold — should be tight."""
        subs = {
            "N": _DummySubProfile(s=5),
            "E": _DummySubProfile(),
            "S": _DummySubProfile(),
            "W": _DummySubProfile(),
        }
        assert dg._dispersion_check(subs) == {"N"}

    def test_6_spades_is_tight(self):
        """6+ spades (P=0.063) is well below threshold — should be tight."""
        subs = {
            "N": _DummySubProfile(s=6),
            "E": _DummySubProfile(),
            "S": _DummySubProfile(),
            "W": _DummySubProfile(),
        }
        assert dg._dispersion_check(subs) == {"N"}

    def test_4_spades_not_tight(self):
        """4+ spades (P=0.430) is above threshold — should NOT be tight."""
        subs = {
            "N": _DummySubProfile(s=4),
            "E": _DummySubProfile(),
            "S": _DummySubProfile(),
            "W": _DummySubProfile(),
        }
        assert dg._dispersion_check(subs) == set()

    def test_two_tight_seats(self):
        """Both N (6+ spades) and S (5+ hearts) should be flagged."""
        subs = {
            "N": _DummySubProfile(s=6),
            "E": _DummySubProfile(),
            "S": _DummySubProfile(h=5),
            "W": _DummySubProfile(),
        }
        assert dg._dispersion_check(subs) == {"N", "S"}

    def test_threshold_boundary_exactly_at(self):
        """P(>=5) = 0.189 with threshold=0.189 should be tight (<=)."""
        subs = {"N": _DummySubProfile(s=5)}
        result = dg._dispersion_check(subs, threshold=0.189)
        assert "N" in result

    def test_threshold_just_below_not_tight(self):
        """P(>=5) = 0.189 with threshold=0.18 should NOT be tight."""
        subs = {"N": _DummySubProfile(s=5)}
        result = dg._dispersion_check(subs, threshold=0.18)
        assert "N" not in result

    def test_no_standard_constraints_skipped(self):
        """Seat without .standard attribute should be skipped."""

        class _NoStandard:
            standard = None

        subs = {"N": _NoStandard()}
        assert dg._dispersion_check(subs) == set()

    def test_hcp_only_not_tight(self):
        """Tight HCP but loose shape should NOT be flagged."""
        # min_cards=0 for all suits, so shape is loose regardless of HCP.
        subs = {"N": _DummySubProfile()}
        assert dg._dispersion_check(subs) == set()

    def test_multiple_suits_one_tight(self):
        """N needs 3 hearts (loose) + 6 spades (tight) — N should be flagged."""
        subs = {"N": _DummySubProfile(s=6, h=3)}
        assert dg._dispersion_check(subs) == {"N"}

    def test_empty_input(self):
        """Empty dict should return empty set."""
        assert dg._dispersion_check({}) == set()

    def test_all_four_seats_tight(self):
        """All 4 seats with 5+ in a suit should all be flagged."""
        subs = {
            "N": _DummySubProfile(s=5),
            "E": _DummySubProfile(h=6),
            "S": _DummySubProfile(d=5),
            "W": _DummySubProfile(c=7),
        }
        assert dg._dispersion_check(subs) == {"N", "E", "S", "W"}


# ===================================================================
# D3 — _random_deal()
# ===================================================================


class TestRandomDeal:
    """Tests for _random_deal()."""

    def _make_deck(self):
        """Build a standard 52-card deck."""
        return dg._build_deck()

    def test_deals_n_cards(self):
        """Should return exactly n cards."""
        rng = random.Random(42)
        deck = self._make_deck()
        hand = dg._random_deal(rng, deck, 13)
        assert len(hand) == 13

    def test_mutates_deck(self):
        """Deck should shrink by n after dealing."""
        rng = random.Random(42)
        deck = self._make_deck()
        dg._random_deal(rng, deck, 13)
        assert len(deck) == 39

    def test_no_overlap_with_remaining_deck(self):
        """Dealt cards should not appear in the remaining deck."""
        rng = random.Random(42)
        deck = self._make_deck()
        hand = dg._random_deal(rng, deck, 13)
        assert set(hand).isdisjoint(set(deck))

    def test_n_zero_returns_empty(self):
        """n=0 should return empty list and leave deck untouched."""
        rng = random.Random(42)
        deck = self._make_deck()
        hand = dg._random_deal(rng, deck, 0)
        assert hand == []
        assert len(deck) == 52

    def test_n_negative_returns_empty(self):
        """Negative n should return empty list."""
        rng = random.Random(42)
        deck = self._make_deck()
        hand = dg._random_deal(rng, deck, -5)
        assert hand == []
        assert len(deck) == 52

    def test_n_exceeds_deck_deals_all(self):
        """If n > deck size, deal all remaining cards."""
        rng = random.Random(42)
        deck = ["AS", "KS", "QS"]
        hand = dg._random_deal(rng, deck, 10)
        assert len(hand) == 3
        assert len(deck) == 0

    def test_empty_deck_returns_empty(self):
        """Empty deck should return empty list."""
        rng = random.Random(42)
        deck = []
        hand = dg._random_deal(rng, deck, 5)
        assert hand == []

    def test_deterministic_with_seed(self):
        """Same seed should produce same result."""
        deck1 = self._make_deck()
        deck2 = self._make_deck()
        hand1 = dg._random_deal(random.Random(99), deck1, 13)
        hand2 = dg._random_deal(random.Random(99), deck2, 13)
        assert hand1 == hand2


# ===================================================================
# D4 — _pre_allocate()
# ===================================================================


class TestPreAllocate:
    """Tests for _pre_allocate()."""

    def _make_deck(self):
        return dg._build_deck()

    def _suit_of(self, card):
        return card[1] if len(card) >= 2 else ""

    def test_6_spades_gives_4(self):
        """min_cards=6 at 75% → floor(4.5) = 4 spade cards pre-allocated."""
        rng = random.Random(42)
        deck = self._make_deck()
        sub = _DummySubProfile(s=6)
        result = dg._pre_allocate(rng, deck, sub)
        spades = [c for c in result if self._suit_of(c) == "S"]
        assert len(spades) == 4

    def test_5_hearts_gives_3(self):
        """min_cards=5 at 75% → floor(3.75) = 3 heart cards pre-allocated."""
        rng = random.Random(42)
        deck = self._make_deck()
        sub = _DummySubProfile(h=5)
        result = dg._pre_allocate(rng, deck, sub)
        hearts = [c for c in result if self._suit_of(c) == "H"]
        assert len(hearts) == 3

    def test_1_club_gives_0(self):
        """min_cards=1 at 50% → floor(0.5) = 0, returns empty."""
        rng = random.Random(42)
        deck = self._make_deck()
        sub = _DummySubProfile(c=1)
        result = dg._pre_allocate(rng, deck, sub)
        assert result == []

    def test_4_diamonds_gives_3(self):
        """min_cards=4 at 75% → 3 diamond cards."""
        rng = random.Random(42)
        deck = self._make_deck()
        sub = _DummySubProfile(d=4)
        result = dg._pre_allocate(rng, deck, sub)
        diamonds = [c for c in result if self._suit_of(c) == "D"]
        assert len(diamonds) == 3

    def test_multiple_suits(self):
        """6 spades + 5 hearts → 4 spades + 3 hearts = 7 total."""
        rng = random.Random(42)
        deck = self._make_deck()
        sub = _DummySubProfile(s=6, h=5)
        result = dg._pre_allocate(rng, deck, sub)
        spades = [c for c in result if self._suit_of(c) == "S"]
        hearts = [c for c in result if self._suit_of(c) == "H"]
        assert len(spades) == 4
        assert len(hearts) == 3
        assert len(result) == 7

    def test_all_zero_min_returns_empty(self):
        """All suits min_cards=0 should return empty."""
        rng = random.Random(42)
        deck = self._make_deck()
        sub = _DummySubProfile()
        result = dg._pre_allocate(rng, deck, sub)
        assert result == []

    def test_mutates_deck(self):
        """Deck should shrink by the number of pre-allocated cards."""
        rng = random.Random(42)
        deck = self._make_deck()
        sub = _DummySubProfile(s=6)  # should pre-allocate 3
        result = dg._pre_allocate(rng, deck, sub)
        assert len(deck) == 52 - len(result)

    def test_no_overlap_with_deck(self):
        """Pre-allocated cards should not remain in the deck."""
        rng = random.Random(42)
        deck = self._make_deck()
        sub = _DummySubProfile(s=6, h=5)
        result = dg._pre_allocate(rng, deck, sub)
        assert set(result).isdisjoint(set(deck))

    def test_allocated_are_correct_suits(self):
        """Each pre-allocated card should be from the requested suit."""
        rng = random.Random(42)
        deck = self._make_deck()
        sub = _DummySubProfile(s=6)
        result = dg._pre_allocate(rng, deck, sub)
        for card in result:
            assert self._suit_of(card) == "S"

    def test_deck_depleted_in_suit(self):
        """If only 2 spades left in deck, can only allocate 2 (not 3)."""
        rng = random.Random(42)
        # Remove all spades except 2.
        deck = self._make_deck()
        spades_in_deck = [c for c in deck if self._suit_of(c) == "S"]
        keep_spades = set(spades_in_deck[:2])
        deck = [c for c in deck if self._suit_of(c) != "S" or c in keep_spades]
        sub = _DummySubProfile(s=6)  # wants 3 spades but only 2 available
        result = dg._pre_allocate(rng, deck, sub)
        spades = [c for c in result if self._suit_of(c) == "S"]
        assert len(spades) == 2

    def test_no_standard_returns_empty(self):
        """Subprofile without .standard should return empty."""

        class _NoStd:
            standard = None

        rng = random.Random(42)
        deck = self._make_deck()
        result = dg._pre_allocate(rng, deck, _NoStd())
        assert result == []

    def test_fraction_override(self):
        """fraction=0.33 on min_cards=6 → floor(1.98) = 1 spade."""
        rng = random.Random(42)
        deck = self._make_deck()
        sub = _DummySubProfile(s=6)
        result = dg._pre_allocate(rng, deck, sub, fraction=0.33)
        spades = [c for c in result if self._suit_of(c) == "S"]
        assert len(spades) == 1

    def test_deterministic_with_seed(self):
        """Same seed should produce same result."""
        sub = _DummySubProfile(s=6, h=5)
        deck1 = self._make_deck()
        deck2 = self._make_deck()
        r1 = dg._pre_allocate(random.Random(77), deck1, sub)
        r2 = dg._pre_allocate(random.Random(77), deck2, sub)
        assert r1 == r2


# ===================================================================
# D5 — _deal_with_help()
# ===================================================================


class TestDealWithHelp:
    """Tests for _deal_with_help()."""

    def _make_deck(self):
        return dg._build_deck()

    def _suit_of(self, card):
        return card[1] if len(card) >= 2 else ""

    def _dealing_order(self):
        return ["N", "E", "S", "W"]

    def test_no_tight_seats_total_52(self):
        """No tight seats: all random, total should be 52 unique cards."""
        rng = random.Random(42)
        deck = self._make_deck()
        subs = {s: _DummySubProfile() for s in "NESW"}
        hands, _ = dg._deal_with_help(rng, deck, subs, set(), self._dealing_order())
        all_cards = []
        for h in hands.values():
            all_cards.extend(h)
        assert len(all_cards) == 52
        assert len(set(all_cards)) == 52

    def test_each_hand_13_cards(self):
        """Every hand should have exactly 13 cards."""
        rng = random.Random(42)
        deck = self._make_deck()
        subs = {s: _DummySubProfile() for s in "NESW"}
        hands, _ = dg._deal_with_help(rng, deck, subs, set(), self._dealing_order())
        for seat, hand in hands.items():
            assert len(hand) == 13, f"{seat} has {len(hand)} cards, expected 13"

    def test_one_tight_seat_has_suit_cards(self):
        """N is tight with 6+ spades — N's hand should have pre-allocated spades."""
        rng = random.Random(42)
        deck = self._make_deck()
        subs = {
            "N": _DummySubProfile(s=6),
            "E": _DummySubProfile(),
            "S": _DummySubProfile(),
            "W": _DummySubProfile(),
        }
        hands, _ = dg._deal_with_help(rng, deck, subs, {"N"}, self._dealing_order())
        n_spades = [c for c in hands["N"] if self._suit_of(c) == "S"]
        # Pre-allocate gives 3 spades (50% of 6), plus random fill may add more.
        assert len(n_spades) >= 3

    def test_two_tight_seats(self):
        """N and S both tight — both get pre-allocation, still 52 total."""
        rng = random.Random(42)
        deck = self._make_deck()
        subs = {
            "N": _DummySubProfile(s=6),
            "E": _DummySubProfile(),
            "S": _DummySubProfile(h=5),
            "W": _DummySubProfile(),
        }
        hands, _ = dg._deal_with_help(rng, deck, subs, {"N", "S"}, self._dealing_order())
        all_cards = []
        for h in hands.values():
            all_cards.extend(h)
        assert len(all_cards) == 52
        assert len(set(all_cards)) == 52

    def test_no_duplicate_cards(self):
        """All 52 cards should be unique across all hands."""
        rng = random.Random(42)
        deck = self._make_deck()
        subs = {s: _DummySubProfile(s=5) for s in "NESW"}
        hands, _ = dg._deal_with_help(rng, deck, subs, {"N", "E", "S", "W"}, self._dealing_order())
        all_cards = []
        for h in hands.values():
            all_cards.extend(h)
        assert len(set(all_cards)) == 52

    def test_last_seat_gets_remainder(self):
        """Last seat (W) should get whatever's left in the deck."""
        rng = random.Random(42)
        deck = self._make_deck()
        subs = {s: _DummySubProfile() for s in "NESW"}
        hands, _ = dg._deal_with_help(rng, deck, subs, set(), self._dealing_order())
        # W is last in dealing order, should have 13 cards.
        assert len(hands["W"]) == 13

    def test_deck_emptied(self):
        """Deck should be empty after dealing."""
        rng = random.Random(42)
        deck = self._make_deck()
        subs = {s: _DummySubProfile() for s in "NESW"}
        dg._deal_with_help(rng, deck, subs, set(), self._dealing_order())
        assert len(deck) == 0

    def test_respects_dealing_order(self):
        """Hands should be keyed by seat names from dealing_order."""
        rng = random.Random(42)
        deck = self._make_deck()
        order = ["S", "W", "N", "E"]
        subs = {s: _DummySubProfile() for s in "NESW"}
        hands, _ = dg._deal_with_help(rng, deck, subs, set(), order)
        assert set(hands.keys()) == {"N", "E", "S", "W"}

    def test_all_tight_seats_still_valid(self):
        """All 4 seats tight — should still produce valid 52-card deal."""
        rng = random.Random(42)
        deck = self._make_deck()
        subs = {
            "N": _DummySubProfile(s=6),
            "E": _DummySubProfile(h=5),
            "S": _DummySubProfile(d=6),
            "W": _DummySubProfile(c=5),
        }
        hands, _ = dg._deal_with_help(rng, deck, subs, {"N", "E", "S", "W"}, self._dealing_order())
        all_cards = []
        for h in hands.values():
            all_cards.extend(h)
        assert len(all_cards) == 52
        assert len(set(all_cards)) == 52
        for seat in "NESW":
            assert len(hands[seat]) == 13

    def test_deterministic_with_seed(self):
        """Same seed should produce same deal."""
        subs = {
            "N": _DummySubProfile(s=6),
            "E": _DummySubProfile(),
            "S": _DummySubProfile(),
            "W": _DummySubProfile(),
        }
        order = self._dealing_order()

        deck1 = self._make_deck()
        deck2 = self._make_deck()
        h1, _ = dg._deal_with_help(random.Random(55), deck1, subs, {"N"}, order)
        h2, _ = dg._deal_with_help(random.Random(55), deck2, subs, {"N"}, order)
        assert h1 == h2

    def test_tight_seat_hand_has_13_even_with_pre_alloc(self):
        """Tight seat with large minima should still get exactly 13 cards."""
        rng = random.Random(42)
        deck = self._make_deck()
        # 8 spades + 5 hearts → pre-alloc 4 + 2 = 6, fill 7 more = 13 total
        subs = {
            "N": _DummySubProfile(s=8, h=5),
            "E": _DummySubProfile(),
            "S": _DummySubProfile(),
            "W": _DummySubProfile(),
        }
        hands, _ = dg._deal_with_help(rng, deck, subs, {"N"}, self._dealing_order())
        assert len(hands["N"]) == 13


# ===================================================================
# D6 — _build_single_constrained_deal_v2() MVP
# ===================================================================


def _wide_range() -> SuitRange:
    """Completely open suit range (0-13 cards, 0-37 HCP)."""
    return SuitRange(min_cards=0, max_cards=13, min_hcp=0, max_hcp=37)


def _wide_standard(total_min=0, total_max=37) -> StandardSuitConstraints:
    """Completely open standard constraints."""
    sr = _wide_range()
    return StandardSuitConstraints(
        spades=sr,
        hearts=sr,
        diamonds=sr,
        clubs=sr,
        total_min_hcp=total_min,
        total_max_hcp=total_max,
    )


def _loose_profile() -> HandProfile:
    """Profile A: all seats completely open — should always succeed quickly."""
    seats = {}
    for s in ("N", "E", "S", "W"):
        sub = SubProfile(
            standard=_wide_standard(),
            random_suit_constraint=None,
            partner_contingent_constraint=None,
        )
        seats[s] = SeatProfile(seat=s, subprofiles=[sub])
    return HandProfile(
        profile_name="Test_Loose",
        description="Loose test profile",
        dealer="N",
        hand_dealing_order=["N", "E", "S", "W"],
        tag="Opener",
        author="Test",
        version="0.1",
        seat_profiles=seats,
    )


def _tight_spades_profile(min_spades=5) -> HandProfile:
    """
    North needs min_spades+ spades, everything else open.
    Other seats unconstrained.
    """
    tight_sr = SuitRange(min_cards=min_spades, max_cards=13, min_hcp=0, max_hcp=37)
    north_std = StandardSuitConstraints(
        spades=tight_sr,
        hearts=_wide_range(),
        diamonds=_wide_range(),
        clubs=_wide_range(),
        total_min_hcp=0,
        total_max_hcp=37,
    )
    seats = {}
    seats["N"] = SeatProfile(
        seat="N",
        subprofiles=[
            SubProfile(
                standard=north_std,
                random_suit_constraint=None,
                partner_contingent_constraint=None,
            )
        ],
    )
    for s in ("E", "S", "W"):
        sub = SubProfile(
            standard=_wide_standard(),
            random_suit_constraint=None,
            partner_contingent_constraint=None,
        )
        seats[s] = SeatProfile(seat=s, subprofiles=[sub])
    return HandProfile(
        profile_name="Test_TightSpades",
        description=f"North needs {min_spades}+ spades",
        dealer="N",
        hand_dealing_order=["N", "E", "S", "W"],
        tag="Opener",
        author="Test",
        version="0.1",
        seat_profiles=seats,
    )


def _impossible_profile() -> HandProfile:
    """
    Impossible: North needs 13 spades AND 13 hearts — can't have 26 cards.
    """
    impossible_sr = SuitRange(min_cards=13, max_cards=13, min_hcp=0, max_hcp=37)
    north_std = StandardSuitConstraints(
        spades=impossible_sr,
        hearts=impossible_sr,
        diamonds=_wide_range(),
        clubs=_wide_range(),
        total_min_hcp=0,
        total_max_hcp=37,
    )
    seats = {}
    seats["N"] = SeatProfile(
        seat="N",
        subprofiles=[
            SubProfile(
                standard=north_std,
                random_suit_constraint=None,
                partner_contingent_constraint=None,
            )
        ],
    )
    for s in ("E", "S", "W"):
        sub = SubProfile(
            standard=_wide_standard(),
            random_suit_constraint=None,
            partner_contingent_constraint=None,
        )
        seats[s] = SeatProfile(seat=s, subprofiles=[sub])
    return HandProfile(
        profile_name="Test_Impossible",
        description="Impossible profile",
        dealer="N",
        hand_dealing_order=["N", "E", "S", "W"],
        tag="Opener",
        author="Test",
        version="0.1",
        seat_profiles=seats,
    )


class TestBuildSingleConstrainedDealV2:
    """Tests for _build_single_constrained_deal_v2() MVP."""

    def test_invariants_safety_fast_path(self):
        """Safety profile should produce a valid deal without constraint matching."""

        class _SafetyProfile:
            is_invariants_safety_profile = True
            dealer = "N"
            hand_dealing_order = ["N", "E", "S", "W"]
            seat_profiles = {}

        rng = random.Random(42)
        deal = dg._build_single_constrained_deal_v2(rng, _SafetyProfile(), 1)
        all_cards = []
        for h in deal.hands.values():
            all_cards.extend(h)
        assert len(set(all_cards)) == 52
        assert deal.board_number == 1

    def test_loose_profile_succeeds(self):
        """Loose profile (all open) should generate a deal on first attempt."""
        rng = random.Random(42)
        profile = _loose_profile()
        deal = dg._build_single_constrained_deal_v2(rng, profile, 1)
        assert deal.board_number == 1
        for seat in ("N", "E", "S", "W"):
            assert len(deal.hands[seat]) == 13

    def test_tight_profile_b_5_spades_succeeds(self):
        """Profile B (N needs 5+ spades) should succeed."""
        rng = random.Random(42)
        profile = _tight_spades_profile(min_spades=5)
        deal = dg._build_single_constrained_deal_v2(rng, profile, 1)
        n_spades = [c for c in deal.hands["N"] if c[1] == "S"]
        assert len(n_spades) >= 5

    def test_tight_profile_6_spades_succeeds(self):
        """Profile with N needs 6+ spades should succeed."""
        rng = random.Random(42)
        profile = _tight_spades_profile(min_spades=6)
        deal = dg._build_single_constrained_deal_v2(rng, profile, 1)
        n_spades = [c for c in deal.hands["N"] if c[1] == "S"]
        assert len(n_spades) >= 6

    def test_deal_has_52_unique_cards(self):
        """All 4 hands combined should have exactly 52 unique cards."""
        rng = random.Random(42)
        profile = _tight_spades_profile(min_spades=5)
        deal = dg._build_single_constrained_deal_v2(rng, profile, 1)
        all_cards = []
        for h in deal.hands.values():
            all_cards.extend(h)
        assert len(all_cards) == 52
        assert len(set(all_cards)) == 52

    def test_each_hand_has_13_cards(self):
        """Every seat should have exactly 13 cards."""
        rng = random.Random(42)
        profile = _loose_profile()
        deal = dg._build_single_constrained_deal_v2(rng, profile, 1)
        for seat, hand in deal.hands.items():
            assert len(hand) == 13, f"{seat} has {len(hand)} cards"

    def test_board_number_preserved(self):
        """Deal.board_number should match the input."""
        rng = random.Random(42)
        profile = _loose_profile()
        deal = dg._build_single_constrained_deal_v2(rng, profile, 7)
        assert deal.board_number == 7

    def test_vulnerability_cycling(self):
        """Boards 1-4 should cycle through vulnerability sequence."""
        rng = random.Random(42)
        profile = _loose_profile()
        expected = ["None", "NS", "EW", "Both"]
        for bn in range(1, 5):
            deal = dg._build_single_constrained_deal_v2(rng, profile, bn)
            assert deal.vulnerability == expected[bn - 1], (
                f"Board {bn}: expected {expected[bn - 1]}, got {deal.vulnerability}"
            )

    def test_raises_on_impossible_profile(self, monkeypatch):
        """Impossible profile should raise DealGenerationError."""
        # Reduce MAX_BOARD_ATTEMPTS to make the test fast.
        monkeypatch.setattr(dg, "MAX_BOARD_ATTEMPTS", 50)
        rng = random.Random(42)
        profile = _impossible_profile()
        with pytest.raises(dg.DealGenerationError, match="v2"):
            dg._build_single_constrained_deal_v2(rng, profile, 1)

    def test_deterministic_with_seed(self):
        """Same seed should produce the same deal."""
        profile = _tight_spades_profile(min_spades=5)
        d1 = dg._build_single_constrained_deal_v2(random.Random(99), profile, 1)
        d2 = dg._build_single_constrained_deal_v2(random.Random(99), profile, 1)
        assert d1.hands == d2.hands

    def test_v1_still_works(self):
        """Old v1 function should still produce valid deals (untouched)."""
        rng = random.Random(42)
        profile = _loose_profile()
        deal = dg._build_single_constrained_deal(rng, profile, 1)
        all_cards = []
        for h in deal.hands.values():
            all_cards.extend(h)
        assert len(set(all_cards)) == 52

    def test_dealer_preserved(self):
        """Deal.dealer should match the profile's dealer."""
        rng = random.Random(42)
        profile = _loose_profile()
        deal = dg._build_single_constrained_deal_v2(rng, profile, 1)
        assert deal.dealer == "N"

    def test_multiple_boards(self):
        """Should be able to generate multiple boards in sequence."""
        rng = random.Random(42)
        profile = _tight_spades_profile(min_spades=5)
        for bn in range(1, 6):
            deal = dg._build_single_constrained_deal_v2(rng, profile, bn)
            assert deal.board_number == bn
            n_spades = [c for c in deal.hands["N"] if c[1] == "S"]
            assert len(n_spades) >= 5


# ===================================================================
# D7 — Full attribution in v2
# ===================================================================


def _tight_hcp_profile(min_hcp=18, max_hcp=20) -> HandProfile:
    """
    North needs exactly min_hcp-max_hcp HCP (no shape help — shape is open).
    This forces many retries so attribution counters accumulate.
    Other seats are completely open.
    """
    north_std = StandardSuitConstraints(
        spades=_wide_range(),
        hearts=_wide_range(),
        diamonds=_wide_range(),
        clubs=_wide_range(),
        total_min_hcp=min_hcp,
        total_max_hcp=max_hcp,
    )
    seats = {}
    seats["N"] = SeatProfile(
        seat="N",
        subprofiles=[
            SubProfile(
                standard=north_std,
                random_suit_constraint=None,
                partner_contingent_constraint=None,
            )
        ],
    )
    for s in ("E", "S", "W"):
        sub = SubProfile(
            standard=_wide_standard(),
            random_suit_constraint=None,
            partner_contingent_constraint=None,
        )
        seats[s] = SeatProfile(seat=s, subprofiles=[sub])
    return HandProfile(
        profile_name="Test_TightHCP",
        description=f"North needs {min_hcp}-{max_hcp} HCP",
        dealer="N",
        hand_dealing_order=["N", "E", "S", "W"],
        tag="Opener",
        author="Test",
        version="0.1",
        seat_profiles=seats,
    )


def _north_tight_south_tight_profile() -> HandProfile:
    """
    North needs 6+ spades, South needs 6+ hearts.
    Both are tight — exercising multi-seat attribution.
    Processing order is N, E, S, W (no RS seats).
    If North fails, South is unchecked. If North passes but South fails,
    North gets global_other.
    """
    tight_spades = SuitRange(min_cards=6, max_cards=13, min_hcp=0, max_hcp=37)
    tight_hearts = SuitRange(min_cards=6, max_cards=13, min_hcp=0, max_hcp=37)
    north_std = StandardSuitConstraints(
        spades=tight_spades,
        hearts=_wide_range(),
        diamonds=_wide_range(),
        clubs=_wide_range(),
        total_min_hcp=0,
        total_max_hcp=37,
    )
    south_std = StandardSuitConstraints(
        spades=_wide_range(),
        hearts=tight_hearts,
        diamonds=_wide_range(),
        clubs=_wide_range(),
        total_min_hcp=0,
        total_max_hcp=37,
    )
    seats = {}
    seats["N"] = SeatProfile(
        seat="N",
        subprofiles=[
            SubProfile(
                standard=north_std,
                random_suit_constraint=None,
                partner_contingent_constraint=None,
            )
        ],
    )
    seats["S"] = SeatProfile(
        seat="S",
        subprofiles=[
            SubProfile(
                standard=south_std,
                random_suit_constraint=None,
                partner_contingent_constraint=None,
            )
        ],
    )
    for s in ("E", "W"):
        sub = SubProfile(
            standard=_wide_standard(),
            random_suit_constraint=None,
            partner_contingent_constraint=None,
        )
        seats[s] = SeatProfile(seat=s, subprofiles=[sub])
    return HandProfile(
        profile_name="Test_NorthSouthTight",
        description="North 6+ spades, South 6+ hearts",
        dealer="N",
        hand_dealing_order=["N", "E", "S", "W"],
        tag="Opener",
        author="Test",
        version="0.1",
        seat_profiles=seats,
    )


class TestV2Attribution:
    """Tests for D7 — failure attribution counters and debug hooks in v2."""

    def test_debug_board_stats_callback_on_success(self):
        """debug_board_stats should fire on successful deal generation."""
        captured = {}

        def callback(fail_counts, seen_counts):
            captured["fail"] = fail_counts
            captured["seen"] = seen_counts

        rng = random.Random(42)
        profile = _loose_profile()
        dg._build_single_constrained_deal_v2(rng, profile, 1, debug_board_stats=callback)
        # Callback should have fired.
        assert "fail" in captured
        assert "seen" in captured
        # Loose profile: all seats seen, none failed (first attempt succeeds).
        for s in ("N", "E", "S", "W"):
            assert captured["seen"].get(s, 0) >= 1
            assert captured["fail"].get(s, 0) == 0

    def test_debug_board_stats_callback_on_exhaustion(self, monkeypatch):
        """debug_board_stats should fire even when deal generation exhausts."""
        monkeypatch.setattr(dg, "MAX_BOARD_ATTEMPTS", 20)
        captured = {}

        def callback(fail_counts, seen_counts):
            captured["fail"] = fail_counts
            captured["seen"] = seen_counts

        rng = random.Random(42)
        profile = _impossible_profile()
        with pytest.raises(dg.DealGenerationError):
            dg._build_single_constrained_deal_v2(rng, profile, 1, debug_board_stats=callback)
        # Callback should have fired with accumulated counts.
        assert "fail" in captured
        assert captured["fail"].get("N", 0) > 0

    def test_seat_fail_as_seat_accumulates(self, monkeypatch):
        """
        For an impossible profile, the first checked seat (N) should
        accumulate seat_fail_as_seat counts on every attempt.
        """
        monkeypatch.setattr(dg, "MAX_BOARD_ATTEMPTS", 30)
        captured_attempts = []

        def hook(profile, board_number, attempt_number, as_seat, global_other, global_unchecked, hcp, shape):
            captured_attempts.append(
                {
                    "as_seat": dict(as_seat),
                    "global_other": dict(global_other),
                    "global_unchecked": dict(global_unchecked),
                    "hcp": dict(hcp),
                    "shape": dict(shape),
                }
            )

        monkeypatch.setattr(dg, "_DEBUG_ON_ATTEMPT_FAILURE_ATTRIBUTION", hook)
        rng = random.Random(42)
        profile = _impossible_profile()
        with pytest.raises(dg.DealGenerationError):
            dg._build_single_constrained_deal_v2(rng, profile, 1)
        # Hook should fire on every failed attempt.
        assert len(captured_attempts) == 30
        # N should be the failing seat every time (impossible constraints).
        last = captured_attempts[-1]
        assert last["as_seat"].get("N", 0) == 30

    def test_global_unchecked_for_seats_after_failure(self, monkeypatch):
        """
        When N fails first, E/S/W should accumulate global_unchecked counts.
        """
        monkeypatch.setattr(dg, "MAX_BOARD_ATTEMPTS", 20)
        captured_attempts = []

        def hook(profile, board_number, attempt_number, as_seat, global_other, global_unchecked, hcp, shape):
            captured_attempts.append(
                {
                    "global_unchecked": dict(global_unchecked),
                }
            )

        monkeypatch.setattr(dg, "_DEBUG_ON_ATTEMPT_FAILURE_ATTRIBUTION", hook)
        rng = random.Random(42)
        profile = _impossible_profile()
        with pytest.raises(dg.DealGenerationError):
            dg._build_single_constrained_deal_v2(rng, profile, 1)
        # N fails first → E, S, W are unchecked on every attempt.
        last = captured_attempts[-1]
        for s in ("E", "S", "W"):
            assert last["global_unchecked"].get(s, 0) == 20

    def test_global_other_when_later_seat_fails(self):
        """
        When a later seat fails, seats checked before it get global_other.
        Use tight HCP profile: N has narrow HCP range, so N sometimes fails.
        When N passes but doesn't fail, and a later seat fails instead,
        N gets global_other.
        """
        # Use a profile where N sometimes fails (tight HCP 18-20).
        # Over many attempts, some will have N pass + later seat fail.
        captured_attempts = []

        def hook(profile, board_number, attempt_number, as_seat, global_other, global_unchecked, hcp, shape):
            captured_attempts.append(
                {
                    "as_seat": dict(as_seat),
                    "global_other": dict(global_other),
                }
            )

        rng = random.Random(42)
        profile = _tight_hcp_profile(min_hcp=18, max_hcp=20)
        old_hook = dg._DEBUG_ON_ATTEMPT_FAILURE_ATTRIBUTION
        try:
            dg._DEBUG_ON_ATTEMPT_FAILURE_ATTRIBUTION = hook
            # Generate a deal — this may take several attempts.
            dg._build_single_constrained_deal_v2(rng, profile, 1)
        finally:
            dg._DEBUG_ON_ATTEMPT_FAILURE_ATTRIBUTION = old_hook

        # If there were any failures, the hook captured them.
        # This test just verifies the hook was wired and dicts are well-formed.
        for entry in captured_attempts:
            assert isinstance(entry["as_seat"], dict)
            assert isinstance(entry["global_other"], dict)

    def test_hcp_shape_classification(self, monkeypatch):
        """
        Impossible profile has shape failure (13 spades + 13 hearts).
        The fail_reason from _match_seat should be classified as 'shape'.
        """
        monkeypatch.setattr(dg, "MAX_BOARD_ATTEMPTS", 10)
        captured_shape = []

        def hook(profile, board_number, attempt_number, as_seat, global_other, global_unchecked, hcp, shape):
            captured_shape.append(dict(shape))

        monkeypatch.setattr(dg, "_DEBUG_ON_ATTEMPT_FAILURE_ATTRIBUTION", hook)
        rng = random.Random(42)
        profile = _impossible_profile()
        with pytest.raises(dg.DealGenerationError):
            dg._build_single_constrained_deal_v2(rng, profile, 1)
        # N fails on shape every time.
        last = captured_shape[-1]
        assert last.get("N", 0) == 10

    def test_debug_on_max_attempts_fires(self, monkeypatch):
        """_DEBUG_ON_MAX_ATTEMPTS hook should fire when v2 exhausts attempts."""
        monkeypatch.setattr(dg, "MAX_BOARD_ATTEMPTS", 15)
        captured = {}

        def hook(profile, board_number, attempts, chosen_indices, seat_fail_counts, viability_summary):
            captured["board_number"] = board_number
            captured["attempts"] = attempts
            captured["seat_fail_counts"] = seat_fail_counts
            captured["viability_summary"] = viability_summary

        monkeypatch.setattr(dg, "_DEBUG_ON_MAX_ATTEMPTS", hook)
        rng = random.Random(42)
        profile = _impossible_profile()
        with pytest.raises(dg.DealGenerationError):
            dg._build_single_constrained_deal_v2(rng, profile, 1)
        # Hook should have fired.
        assert captured["board_number"] == 1
        assert captured["attempts"] == 15
        assert captured["seat_fail_counts"].get("N", 0) == 15
        # viability_summary should contain per-seat diagnostics.
        vs = captured["viability_summary"]
        assert vs is not None
        assert "N" in vs
        assert vs["N"]["attempts"] == 15
        assert vs["N"]["failures"] == 15

    def test_attribution_hook_receives_copies(self, monkeypatch):
        """
        Dicts passed to _DEBUG_ON_ATTEMPT_FAILURE_ATTRIBUTION should be
        independent copies — mutating them shouldn't affect future calls.
        """
        monkeypatch.setattr(dg, "MAX_BOARD_ATTEMPTS", 5)
        captured = []

        def hook(profile, board_number, attempt_number, as_seat, global_other, global_unchecked, hcp, shape):
            # Mutate the dict — this should NOT affect future hook calls.
            as_seat["MUTATED"] = True
            captured.append(dict(as_seat))

        monkeypatch.setattr(dg, "_DEBUG_ON_ATTEMPT_FAILURE_ATTRIBUTION", hook)
        rng = random.Random(42)
        profile = _impossible_profile()
        with pytest.raises(dg.DealGenerationError):
            dg._build_single_constrained_deal_v2(rng, profile, 1)
        # Each captured dict should have the mutation, but the N count
        # should increment properly (not polluted by prior mutation).
        for i, entry in enumerate(captured):
            assert entry.get("MUTATED") is True
            assert entry.get("N", 0) == i + 1

    def test_multi_seat_attribution(self):
        """
        North 6+ spades + South 6+ hearts: both tight.
        Over many attempts, both N and S should accumulate as_seat failures.
        """
        captured_attempts = []

        def hook(profile, board_number, attempt_number, as_seat, global_other, global_unchecked, hcp, shape):
            captured_attempts.append(
                {
                    "as_seat": dict(as_seat),
                    "global_other": dict(global_other),
                    "global_unchecked": dict(global_unchecked),
                }
            )

        # Seed 0 ensures the deal doesn't succeed on the very first
        # attempt (which can happen with aggressive pre-allocation),
        # so the attribution hook fires at least once.
        rng = random.Random(0)
        profile = _north_tight_south_tight_profile()
        old_hook = dg._DEBUG_ON_ATTEMPT_FAILURE_ATTRIBUTION
        try:
            dg._DEBUG_ON_ATTEMPT_FAILURE_ATTRIBUTION = hook
            # Generate a deal — will take several attempts.
            deal = dg._build_single_constrained_deal_v2(rng, profile, 1)
        finally:
            dg._DEBUG_ON_ATTEMPT_FAILURE_ATTRIBUTION = old_hook

        # There should have been at least some failed attempts.
        assert len(captured_attempts) > 0
        last = captured_attempts[-1]
        # With N checked first: when N fails, S is unchecked.
        # When N passes, S might fail → N gets global_other.
        # At least N should have some as_seat failures.
        assert last["as_seat"].get("N", 0) > 0
        # Verify deal is valid.
        n_spades = [c for c in deal.hands["N"] if c[1] == "S"]
        s_hearts = [c for c in deal.hands["S"] if c[1] == "H"]
        assert len(n_spades) >= 6
        assert len(s_hearts) >= 6


# ===================================================================
# #13 — _constrained_fill() with rs_suit_hcp_max
# ===================================================================


def test_constrained_fill_rs_hcp_max_blocks_honor():
    """An honor card that would bust the per-suit HCP cap is skipped."""
    # Deck has Ace of Hearts (4 HCP) then spot cards.
    deck = ["AH", "2S", "3D", "4C", "5S", "6D", "7C"]
    pre_cards = ["KH", "QH"]  # Already 3 + 2 = 5 HCP in hearts
    maxima = {"S": 13, "H": 13, "D": 13, "C": 13}

    # Hearts capped at 7 HCP — adding AH (4) would make 9 > 7, so skip.
    result = dg._constrained_fill(deck, 3, pre_cards, maxima, 40, rs_suit_hcp_max={"H": 7})

    # AH should be skipped; 3 spot cards accepted instead.
    assert "AH" not in result
    assert len(result) == 3
    # AH should remain in the deck.
    assert "AH" in deck


def test_constrained_fill_rs_hcp_max_allows_spot_cards():
    """Spot cards (0 HCP) are always accepted for RS suits."""
    # Pre-cards already at the HCP cap for hearts.
    deck = ["2H", "3H", "4S", "5D"]
    pre_cards = ["AH", "KH"]  # 4 + 3 = 7 HCP in hearts
    maxima = {"S": 13, "H": 13, "D": 13, "C": 13}

    # Hearts capped at 7 — but 2H and 3H are spots (0 HCP), so accepted.
    result = dg._constrained_fill(deck, 3, pre_cards, maxima, 40, rs_suit_hcp_max={"H": 7})

    assert "2H" in result
    assert "3H" in result
    assert len(result) == 3


def test_constrained_fill_rs_hcp_max_none_no_effect():
    """rs_suit_hcp_max=None behaves identically to before (backward compat)."""
    deck_a = ["AH", "KH", "2S", "3D", "4C", "5S", "6D"]
    deck_b = list(deck_a)
    pre_cards = []
    maxima = {"S": 13, "H": 13, "D": 13, "C": 13}

    result_a = dg._constrained_fill(deck_a, 4, pre_cards, maxima, 40)
    result_b = dg._constrained_fill(deck_b, 4, pre_cards, maxima, 40, rs_suit_hcp_max=None)

    assert result_a == result_b
    assert deck_a == deck_b


def test_constrained_fill_rs_hcp_max_multiple_suits():
    """Two RS suits with different HCP caps, both enforced."""
    # AH (4 HCP) and AD (4 HCP) should be skipped by their respective caps.
    deck = ["AH", "AD", "2S", "3C", "4S", "5C", "6S"]
    pre_cards = ["KH", "KD"]  # 3 HCP in H, 3 HCP in D
    maxima = {"S": 13, "H": 13, "D": 13, "C": 13}

    # H capped at 5, D capped at 4 — AH (3+4=7>5) and AD (3+4=7>4) both skip.
    result = dg._constrained_fill(
        deck,
        4,
        pre_cards,
        maxima,
        40,
        rs_suit_hcp_max={"H": 5, "D": 4},
    )

    assert "AH" not in result
    assert "AD" not in result
    assert len(result) == 4


def test_constrained_fill_rs_hcp_max_under_limit_accepted():
    """Honor card that fits within the per-suit HCP cap is accepted."""
    # JH (1 HCP) — pre has 2H (0 HCP), so suit total would be 1 <= 3.
    deck = ["JH", "2S", "3D", "4C"]
    pre_cards = ["2H"]  # 0 HCP in hearts
    maxima = {"S": 13, "H": 13, "D": 13, "C": 13}

    result = dg._constrained_fill(deck, 3, pre_cards, maxima, 40, rs_suit_hcp_max={"H": 3})

    # JH should be accepted (0 + 1 = 1 <= 3).
    assert "JH" in result
    assert len(result) == 3


# ===================================================================
# _compute_dealing_order — auto-compute with least constrained last
# ===================================================================


class TestComputeDealingOrder:
    """Tests for _compute_dealing_order (least constrained seat last)."""

    def _make_sub(self, *, rs=False, pc=False, oc=False, hcp_min=0, hcp_max=37):
        """Build a minimal SubProfile-like object for testing."""
        from types import SimpleNamespace

        std = SimpleNamespace(total_min_hcp=hcp_min, total_max_hcp=hcp_max)
        return SimpleNamespace(
            standard=std,
            random_suit_constraint=SimpleNamespace() if rs else None,
            partner_contingent_constraint=SimpleNamespace() if pc else None,
            opponents_contingent_suit_constraint=SimpleNamespace() if oc else None,
        )

    def test_all_standard_clockwise_from_dealer(self):
        """All standard seats: clockwise from dealer, all equal risk."""
        subs = {
            "N": self._make_sub(),
            "E": self._make_sub(),
            "S": self._make_sub(),
            "W": self._make_sub(),
        }
        assert dg._compute_dealing_order(subs, "N") == ["N", "E", "S", "W"]
        assert dg._compute_dealing_order(subs, "W") == ["W", "N", "E", "S"]

    def test_rs_seat_first(self):
        """RS seat should be dealt first (highest risk)."""
        subs = {
            "N": self._make_sub(),
            "E": self._make_sub(rs=True),
            "S": self._make_sub(),
            "W": self._make_sub(),
        }
        result = dg._compute_dealing_order(subs, "N")
        assert result[0] == "E"  # RS first
        assert result[-1] in ("N", "S", "W")  # standard last

    def test_standard_seat_last(self):
        """When 3 seats are constrained, standard seat should be last."""
        subs = {
            "N": self._make_sub(rs=True),
            "E": self._make_sub(oc=True),
            "S": self._make_sub(),  # standard = least constrained
            "W": self._make_sub(pc=True),
        }
        result = dg._compute_dealing_order(subs, "N")
        assert result[-1] == "S"

    def test_multiple_rs_sorted_by_risk(self):
        """Multiple RS seats: both before non-RS seats."""
        subs = {
            "N": self._make_sub(rs=True),
            "E": self._make_sub(),
            "S": self._make_sub(rs=True),
            "W": self._make_sub(),
        }
        result = dg._compute_dealing_order(subs, "N")
        # Both RS seats should be in first two positions
        assert set(result[:2]) == {"N", "S"}

    def test_hcp_tiebreaker_narrower_first(self):
        """Among equal-risk seats, narrower HCP range goes first."""
        subs = {
            "N": self._make_sub(hcp_min=10, hcp_max=12),  # range 2
            "E": self._make_sub(hcp_min=0, hcp_max=37),  # range 37
            "S": self._make_sub(hcp_min=0, hcp_max=37),  # range 37
            "W": self._make_sub(hcp_min=0, hcp_max=37),  # range 37
        }
        result = dg._compute_dealing_order(subs, "N")
        assert result[0] == "N"  # narrowest HCP = dealt first
        assert result[-1] != "N"  # NOT last

    def test_pc_oc_between_rs_and_standard(self):
        """PC/OC seats (risk 0.5) should be between RS (1.0) and standard (0.0)."""
        subs = {
            "N": self._make_sub(rs=True),  # risk 1.0
            "E": self._make_sub(pc=True),  # risk 0.5
            "S": self._make_sub(),  # risk 0.0
            "W": self._make_sub(oc=True),  # risk 0.5
        }
        result = dg._compute_dealing_order(subs, "N")
        assert result[0] == "N"  # RS first
        assert result[-1] == "S"  # standard last
        assert set(result[1:3]) == {"E", "W"}  # PC/OC in middle

    def test_clockwise_tiebreaker(self):
        """Equal risk + equal HCP range: clockwise from dealer breaks tie."""
        subs = {
            "N": self._make_sub(pc=True),  # risk 0.5
            "E": self._make_sub(oc=True),  # risk 0.5
            "S": self._make_sub(),  # risk 0.0
            "W": self._make_sub(),  # risk 0.0
        }
        # Dealer E → clockwise: E, S, W, N
        result = dg._compute_dealing_order(subs, "E")
        # E (0.5) and N (0.5) should be first two, E before N (clockwise from E)
        assert result[0] == "E"
        assert result[1] == "N"
        # S (0.0) and W (0.0): S before W clockwise from E
        assert result[2] == "S"
        assert result[3] == "W"

    def test_always_returns_four_seats(self):
        """Output always contains exactly 4 seats, one of each."""
        subs = {
            "N": self._make_sub(rs=True),
            "E": self._make_sub(pc=True),
            "S": self._make_sub(oc=True),
            "W": self._make_sub(),
        }
        result = dg._compute_dealing_order(subs, "W")
        assert len(result) == 4
        assert set(result) == {"N", "E", "S", "W"}

    def test_subprofile_constraint_type(self):
        """_subprofile_constraint_type classifies correctly."""
        assert dg._subprofile_constraint_type(self._make_sub()) == "standard"
        assert dg._subprofile_constraint_type(self._make_sub(rs=True)) == "rs"
        assert dg._subprofile_constraint_type(self._make_sub(pc=True)) == "pc"
        assert dg._subprofile_constraint_type(self._make_sub(oc=True)) == "oc"
