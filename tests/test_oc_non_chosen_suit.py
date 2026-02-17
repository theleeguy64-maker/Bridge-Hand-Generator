# tests/test_oc_non_chosen_suit.py
"""
Tests for the OC non-chosen-suit feature.

When use_non_chosen_suit=True on an OpponentContingentSuitData, the OC
matching targets the suit the opponent did NOT choose (the inverse of
the normal behaviour which targets the first chosen suit).
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pytest

from bridge_engine.hand_profile_model import (
    OpponentContingentSuitData,
    RandomSuitConstraintData,
    StandardSuitConstraints,
    SuitRange,
)
from bridge_engine.seat_viability import (
    SuitAnalysis,
    _compute_suit_analysis,
    _match_subprofile,
)
from bridge_engine.deal_generator_v2 import _compute_rs_allowed_suits


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

Seat = str


def _open_range() -> SuitRange:
    """Fully open suit range — no constraint."""
    return SuitRange(min_cards=0, max_cards=13, min_hcp=0, max_hcp=37)


def _make_standard() -> StandardSuitConstraints:
    """Unconstrained standard constraints."""
    return StandardSuitConstraints(
        spades=_open_range(),
        hearts=_open_range(),
        diamonds=_open_range(),
        clubs=_open_range(),
    )


@dataclass
class FakeSubProfile:
    """Minimal SubProfile stand-in for unit tests."""

    standard: StandardSuitConstraints = field(default_factory=_make_standard)
    random_suit_constraint: Optional[RandomSuitConstraintData] = None
    partner_contingent_constraint: Optional[Any] = None
    opponents_contingent_suit_constraint: Optional[OpponentContingentSuitData] = None
    weight_percent: float = 100.0
    ns_role_usage: str = "any"
    subprofile_exclusions: Optional[Any] = None


def _hand_with_suit_lengths(s: int, h: int, d: int, c: int) -> List[str]:
    """Build a 13-card hand with the specified suit lengths."""
    ranks = "AKQJT98765432"
    hand: List[str] = []
    for suit_char, count in [("S", s), ("H", h), ("D", d), ("C", c)]:
        for i in range(count):
            hand.append(f"{ranks[i]}{suit_char}")
    assert len(hand) == 13, f"Total cards must be 13, got {s + h + d + c}"
    return hand


# ---------------------------------------------------------------------------
# 1. Data model round-trip
# ---------------------------------------------------------------------------


class TestDataModelRoundTrip:
    def test_to_dict_includes_use_non_chosen_suit_true(self) -> None:
        oc = OpponentContingentSuitData(
            opponent_seat="W",
            suit_range=SuitRange(min_cards=5, max_cards=6, min_hcp=2, max_hcp=7),
            use_non_chosen_suit=True,
        )
        d = oc.to_dict()
        assert d["use_non_chosen_suit"] is True
        assert d["opponent_seat"] == "W"

    def test_to_dict_includes_use_non_chosen_suit_false(self) -> None:
        oc = OpponentContingentSuitData(
            opponent_seat="E",
            suit_range=SuitRange(),
        )
        d = oc.to_dict()
        assert d["use_non_chosen_suit"] is False

    def test_from_dict_with_flag_true(self) -> None:
        data = {
            "opponent_seat": "W",
            "suit_range": {"min_cards": 5, "max_cards": 6, "min_hcp": 2, "max_hcp": 7},
            "use_non_chosen_suit": True,
        }
        oc = OpponentContingentSuitData.from_dict(data)
        assert oc.use_non_chosen_suit is True
        assert oc.opponent_seat == "W"
        assert oc.suit_range.min_cards == 5

    def test_from_dict_backward_compat_missing_key(self) -> None:
        """Old JSON without use_non_chosen_suit should default to False."""
        data = {
            "opponent_seat": "E",
            "suit_range": {"min_cards": 0, "max_cards": 13},
        }
        oc = OpponentContingentSuitData.from_dict(data)
        assert oc.use_non_chosen_suit is False

    def test_round_trip(self) -> None:
        oc = OpponentContingentSuitData(
            opponent_seat="W",
            suit_range=SuitRange(min_cards=5, max_cards=6, min_hcp=2, max_hcp=7),
            use_non_chosen_suit=True,
        )
        restored = OpponentContingentSuitData.from_dict(oc.to_dict())
        assert restored == oc


# ---------------------------------------------------------------------------
# 2. _compute_rs_allowed_suits helper
# ---------------------------------------------------------------------------


class TestComputeRsAllowedSuits:
    def test_extracts_allowed_suits_from_rs_subprofile(self) -> None:
        rs = RandomSuitConstraintData(
            required_suits_count=1,
            allowed_suits=["S", "H"],
            suit_ranges=[SuitRange(min_cards=6, max_cards=6)],
            pair_overrides=[],
        )
        sub = FakeSubProfile(random_suit_constraint=rs)
        result = _compute_rs_allowed_suits({"W": sub})  # type: ignore[arg-type]
        assert result == {"W": ["S", "H"]}

    def test_skips_non_rs_seats(self) -> None:
        sub = FakeSubProfile(random_suit_constraint=None)
        result = _compute_rs_allowed_suits({"N": sub})  # type: ignore[arg-type]
        assert result == {}

    def test_multiple_seats(self) -> None:
        rs_w = RandomSuitConstraintData(
            required_suits_count=1,
            allowed_suits=["S", "H"],
            suit_ranges=[SuitRange(min_cards=6, max_cards=6)],
            pair_overrides=[],
        )
        rs_e = RandomSuitConstraintData(
            required_suits_count=1,
            allowed_suits=["D", "C"],
            suit_ranges=[SuitRange(min_cards=5, max_cards=5)],
            pair_overrides=[],
        )
        result = _compute_rs_allowed_suits(
            {  # type: ignore[arg-type]
                "W": FakeSubProfile(random_suit_constraint=rs_w),
                "E": FakeSubProfile(random_suit_constraint=rs_e),
                "N": FakeSubProfile(),
            }
        )
        assert result == {"W": ["S", "H"], "E": ["D", "C"]}


# ---------------------------------------------------------------------------
# 3. OC matching — standard (regression)
# ---------------------------------------------------------------------------


class TestOcStandardRegression:
    """Ensure standard OC (use_non_chosen_suit=False) still works."""

    def test_standard_oc_matches_chosen_suit(self) -> None:
        """OC targets W's first chosen suit (H). N has 5H → should match."""
        oc = OpponentContingentSuitData(
            opponent_seat="W",
            suit_range=SuitRange(min_cards=5, max_cards=6, min_hcp=0, max_hcp=37),
            use_non_chosen_suit=False,
        )
        sub = FakeSubProfile(opponents_contingent_suit_constraint=oc)
        hand = _hand_with_suit_lengths(s=3, h=5, d=3, c=2)
        analysis = _compute_suit_analysis(hand)
        rng = random.Random(42)

        matched, _, _ = _match_subprofile(
            analysis=analysis,
            seat="N",
            sub=sub,  # type: ignore[arg-type]
            random_suit_choices={"W": ["H"]},
            rng=rng,
            rs_allowed_suits={"W": ["S", "H"]},
        )
        assert matched is True

    def test_standard_oc_fails_when_chosen_suit_too_short(self) -> None:
        """OC targets W's first chosen suit (H). N has 2H → should fail."""
        oc = OpponentContingentSuitData(
            opponent_seat="W",
            suit_range=SuitRange(min_cards=5, max_cards=6, min_hcp=0, max_hcp=37),
            use_non_chosen_suit=False,
        )
        sub = FakeSubProfile(opponents_contingent_suit_constraint=oc)
        hand = _hand_with_suit_lengths(s=5, h=2, d=3, c=3)
        analysis = _compute_suit_analysis(hand)
        rng = random.Random(42)

        matched, _, _ = _match_subprofile(
            analysis=analysis,
            seat="N",
            sub=sub,  # type: ignore[arg-type]
            random_suit_choices={"W": ["H"]},
            rng=rng,
            rs_allowed_suits={"W": ["S", "H"]},
        )
        assert matched is False


# ---------------------------------------------------------------------------
# 4-5. OC matching — non-chosen suit
# ---------------------------------------------------------------------------


class TestOcNonChosenSuit:
    def test_west_picks_h_north_targets_s(self) -> None:
        """West RS picks H from [S,H] → North OC non-chosen targets S."""
        oc = OpponentContingentSuitData(
            opponent_seat="W",
            suit_range=SuitRange(min_cards=5, max_cards=6, min_hcp=0, max_hcp=37),
            use_non_chosen_suit=True,
        )
        sub = FakeSubProfile(opponents_contingent_suit_constraint=oc)
        # North has 5 spades (the non-chosen suit) → should match
        hand = _hand_with_suit_lengths(s=5, h=3, d=3, c=2)
        analysis = _compute_suit_analysis(hand)
        rng = random.Random(42)

        matched, _, _ = _match_subprofile(
            analysis=analysis,
            seat="N",
            sub=sub,  # type: ignore[arg-type]
            random_suit_choices={"W": ["H"]},
            rng=rng,
            rs_allowed_suits={"W": ["S", "H"]},
        )
        assert matched is True

    def test_west_picks_s_north_targets_h(self) -> None:
        """West RS picks S from [S,H] → North OC non-chosen targets H."""
        oc = OpponentContingentSuitData(
            opponent_seat="W",
            suit_range=SuitRange(min_cards=5, max_cards=6, min_hcp=0, max_hcp=37),
            use_non_chosen_suit=True,
        )
        sub = FakeSubProfile(opponents_contingent_suit_constraint=oc)
        # North has 5 hearts (the non-chosen suit) → should match
        hand = _hand_with_suit_lengths(s=3, h=5, d=3, c=2)
        analysis = _compute_suit_analysis(hand)
        rng = random.Random(42)

        matched, _, _ = _match_subprofile(
            analysis=analysis,
            seat="N",
            sub=sub,  # type: ignore[arg-type]
            random_suit_choices={"W": ["S"]},
            rng=rng,
            rs_allowed_suits={"W": ["S", "H"]},
        )
        assert matched is True

    def test_non_chosen_fails_when_suit_too_short(self) -> None:
        """West picks H → target is S, but N only has 2S → fail."""
        oc = OpponentContingentSuitData(
            opponent_seat="W",
            suit_range=SuitRange(min_cards=5, max_cards=6, min_hcp=0, max_hcp=37),
            use_non_chosen_suit=True,
        )
        sub = FakeSubProfile(opponents_contingent_suit_constraint=oc)
        hand = _hand_with_suit_lengths(s=2, h=5, d=3, c=3)
        analysis = _compute_suit_analysis(hand)
        rng = random.Random(42)

        matched, _, _ = _match_subprofile(
            analysis=analysis,
            seat="N",
            sub=sub,  # type: ignore[arg-type]
            random_suit_choices={"W": ["H"]},
            rng=rng,
            rs_allowed_suits={"W": ["S", "H"]},
        )
        assert matched is False

    def test_non_chosen_with_hcp_constraint(self) -> None:
        """West picks H → target is S. N has 5S with 2-7 HCP → check HCP."""
        oc = OpponentContingentSuitData(
            opponent_seat="W",
            suit_range=SuitRange(min_cards=5, max_cards=6, min_hcp=2, max_hcp=7),
            use_non_chosen_suit=True,
        )
        sub = FakeSubProfile(opponents_contingent_suit_constraint=oc)
        # Hand: AS KS 5S 4S 3S ... → spade HCP = 4+3 = 7 (A=4,K=3), 5 spades
        hand = ["AS", "KS", "5S", "4S", "3S", "AH", "KH", "QH", "AD", "KD", "AC", "KC", "QC"]
        analysis = _compute_suit_analysis(hand)
        rng = random.Random(42)

        matched, _, _ = _match_subprofile(
            analysis=analysis,
            seat="N",
            sub=sub,  # type: ignore[arg-type]
            random_suit_choices={"W": ["H"]},
            rng=rng,
            rs_allowed_suits={"W": ["S", "H"]},
        )
        assert matched is True


# ---------------------------------------------------------------------------
# 6. Graceful failure — no rs_allowed_suits
# ---------------------------------------------------------------------------


class TestOcNonChosenGracefulFail:
    def test_no_rs_allowed_suits_returns_false(self) -> None:
        """When rs_allowed_suits is None, non-chosen OC fails gracefully."""
        oc = OpponentContingentSuitData(
            opponent_seat="W",
            suit_range=SuitRange(min_cards=5, max_cards=6, min_hcp=0, max_hcp=37),
            use_non_chosen_suit=True,
        )
        sub = FakeSubProfile(opponents_contingent_suit_constraint=oc)
        hand = _hand_with_suit_lengths(s=5, h=3, d=3, c=2)
        analysis = _compute_suit_analysis(hand)
        rng = random.Random(42)

        matched, _, fail_reason = _match_subprofile(
            analysis=analysis,
            seat="N",
            sub=sub,  # type: ignore[arg-type]
            random_suit_choices={"W": ["H"]},
            rng=rng,
            rs_allowed_suits=None,  # No allowed suits info
        )
        assert matched is False
        assert fail_reason == "other"

    def test_all_suits_chosen_returns_false(self) -> None:
        """When opponent chose all allowed suits, non-chosen is empty → fail."""
        oc = OpponentContingentSuitData(
            opponent_seat="W",
            suit_range=SuitRange(min_cards=3, max_cards=6, min_hcp=0, max_hcp=37),
            use_non_chosen_suit=True,
        )
        sub = FakeSubProfile(opponents_contingent_suit_constraint=oc)
        hand = _hand_with_suit_lengths(s=5, h=5, d=2, c=1)
        analysis = _compute_suit_analysis(hand)
        rng = random.Random(42)

        # W chose both S and H from allowed [S, H] — no non-chosen suits
        matched, _, fail_reason = _match_subprofile(
            analysis=analysis,
            seat="N",
            sub=sub,  # type: ignore[arg-type]
            random_suit_choices={"W": ["S", "H"]},
            rng=rng,
            rs_allowed_suits={"W": ["S", "H"]},
        )
        assert matched is False
        assert fail_reason == "other"


# ---------------------------------------------------------------------------
# 7. Validation
# ---------------------------------------------------------------------------


class TestOcNonChosenValidation:
    def test_validation_passes_with_surplus_rs(self) -> None:
        """No error when opponent has RS with allowed > required."""
        from bridge_engine.hand_profile_model import (
            HandProfile,
            SeatProfile,
            SubProfile,
        )
        from bridge_engine.hand_profile_validate import validate_profile

        # W has RS: pick 1 from [S, H] — surplus exists
        w_sub = SubProfile(
            standard=_make_standard(),
            random_suit_constraint=RandomSuitConstraintData(
                required_suits_count=1,
                allowed_suits=["S", "H"],
                suit_ranges=[SuitRange(min_cards=6, max_cards=6)],
                pair_overrides=[],
            ),
        )
        # N has OC non-chosen targeting W
        n_sub = SubProfile(
            standard=_make_standard(),
            opponents_contingent_suit_constraint=OpponentContingentSuitData(
                opponent_seat="W",
                suit_range=SuitRange(min_cards=5, max_cards=6, min_hcp=2, max_hcp=7),
                use_non_chosen_suit=True,
            ),
        )
        e_sub = SubProfile(standard=_make_standard())
        s_sub = SubProfile(standard=_make_standard())

        profile = HandProfile(
            profile_name="Test_OC_NonChosen",
            description="Test",
            tag="Overcaller",
            seat_profiles={
                "N": SeatProfile(seat="N", subprofiles=[n_sub]),
                "E": SeatProfile(seat="E", subprofiles=[e_sub]),
                "S": SeatProfile(seat="S", subprofiles=[s_sub]),
                "W": SeatProfile(seat="W", subprofiles=[w_sub]),
            },
            hand_dealing_order=["W", "N", "E", "S"],
            dealer="N",
        )
        # Should not raise — validate via to_dict round-trip
        result = validate_profile(profile.to_dict())
        assert result is not None

    def test_validation_fails_no_surplus_rs(self) -> None:
        """Error when opponent RS has required == allowed (no non-chosen possible)."""
        from bridge_engine.hand_profile_model import (
            HandProfile,
            SeatProfile,
            SubProfile,
        )
        from bridge_engine.hand_profile_validate import validate_profile
        from bridge_engine.hand_profile_model import ProfileError

        # W has RS: pick 2 from [S, H] — NO surplus (2 == 2)
        w_sub = SubProfile(
            standard=_make_standard(),
            random_suit_constraint=RandomSuitConstraintData(
                required_suits_count=2,
                allowed_suits=["S", "H"],
                suit_ranges=[
                    SuitRange(min_cards=5, max_cards=6),
                    SuitRange(min_cards=5, max_cards=6),
                ],
                pair_overrides=[],
            ),
        )
        # N has OC non-chosen targeting W
        n_sub = SubProfile(
            standard=_make_standard(),
            opponents_contingent_suit_constraint=OpponentContingentSuitData(
                opponent_seat="W",
                suit_range=SuitRange(min_cards=5, max_cards=6),
                use_non_chosen_suit=True,
            ),
        )
        e_sub = SubProfile(standard=_make_standard())
        s_sub = SubProfile(standard=_make_standard())

        profile = HandProfile(
            profile_name="Test_OC_NoSurplus",
            description="Test",
            tag="Overcaller",
            seat_profiles={
                "N": SeatProfile(seat="N", subprofiles=[n_sub]),
                "E": SeatProfile(seat="E", subprofiles=[e_sub]),
                "S": SeatProfile(seat="S", subprofiles=[s_sub]),
                "W": SeatProfile(seat="W", subprofiles=[w_sub]),
            },
            hand_dealing_order=["W", "N", "E", "S"],
            dealer="N",
        )
        with pytest.raises(ProfileError, match="non-chosen-suit OC"):
            validate_profile(profile.to_dict())


# ---------------------------------------------------------------------------
# 8. Integration — full deal generation
# ---------------------------------------------------------------------------


class TestOcNonChosenIntegration:
    def test_generate_deals_with_non_chosen_oc(self, tmp_path) -> None:
        """
        End-to-end: West RS picks 1 from [S,H], North OC non-chosen gets
        the other suit with 5-6 cards. Generate 5 boards and verify.
        """
        from bridge_engine.hand_profile_model import (
            HandProfile,
            SeatProfile,
            SubProfile,
        )
        from bridge_engine.deal_generator import generate_deals
        from bridge_engine.setup_env import run_setup

        # W: RS pick 1 from [S, H], 6 cards in chosen suit
        w_sub = SubProfile(
            standard=_make_standard(),
            random_suit_constraint=RandomSuitConstraintData(
                required_suits_count=1,
                allowed_suits=["S", "H"],
                suit_ranges=[SuitRange(min_cards=6, max_cards=6, min_hcp=0, max_hcp=37)],
                pair_overrides=[],
            ),
        )
        # N: OC non-chosen targeting W, 5-6 cards in the non-chosen suit
        n_sub = SubProfile(
            standard=_make_standard(),
            opponents_contingent_suit_constraint=OpponentContingentSuitData(
                opponent_seat="W",
                suit_range=SuitRange(min_cards=5, max_cards=6, min_hcp=0, max_hcp=37),
                use_non_chosen_suit=True,
            ),
        )
        e_sub = SubProfile(standard=_make_standard())
        s_sub = SubProfile(standard=_make_standard())

        profile = HandProfile(
            profile_name="Test_OC_NonChosen_E2E",
            description="Test",
            tag="Overcaller",
            seat_profiles={
                "N": SeatProfile(seat="N", subprofiles=[n_sub]),
                "E": SeatProfile(seat="E", subprofiles=[e_sub]),
                "S": SeatProfile(seat="S", subprofiles=[s_sub]),
                "W": SeatProfile(seat="W", subprofiles=[w_sub]),
            },
            hand_dealing_order=["W", "N", "E", "S"],
            dealer="N",
        )

        setup = run_setup(
            base_dir=tmp_path / "out",
            owner="TestOwner",
            profile_name=profile.profile_name,
            ask_seed_choice=False,
        )
        deal_set = generate_deals(setup, profile, num_deals=5, enable_rotation=False)

        assert len(deal_set.deals) == 5

        for deal in deal_set.deals:
            w_hand = deal.hands["W"]
            n_hand = deal.hands["N"]

            # Determine which suit W chose (the one with 6 cards)
            w_analysis = _compute_suit_analysis(w_hand)
            w_chosen = None
            for suit in ["S", "H"]:
                if suit in w_analysis.cards_by_suit and len(w_analysis.cards_by_suit[suit]) == 6:
                    w_chosen = suit
                    break
            assert w_chosen is not None, f"W should have exactly 6 cards in S or H: {w_hand}"

            # The non-chosen suit
            non_chosen = "H" if w_chosen == "S" else "S"

            # N should have 5-6 cards in the non-chosen suit
            n_analysis = _compute_suit_analysis(n_hand)
            n_count = len(n_analysis.cards_by_suit.get(non_chosen, []))
            assert 5 <= n_count <= 6, (
                f"Board {deal.board_number}: W chose {w_chosen}, N should have 5-6 {non_chosen} but has {n_count}"
            )


# ---------------------------------------------------------------------------
# 9. Edge cases — 3+ allowed suits, HCP rejection, mixed OC modes
# ---------------------------------------------------------------------------


class TestOcNonChosenEdgeCases:
    def test_three_allowed_suits_targets_first_non_chosen(self) -> None:
        """RS pick 1 from [S, H, D] → if H chosen, non-chosen = [S, D], target S (first)."""
        oc = OpponentContingentSuitData(
            opponent_seat="W",
            suit_range=SuitRange(min_cards=4, max_cards=6, min_hcp=0, max_hcp=37),
            use_non_chosen_suit=True,
        )
        sub = FakeSubProfile(opponents_contingent_suit_constraint=oc)
        # North has 5 spades (first non-chosen suit) → should match
        hand = _hand_with_suit_lengths(s=5, h=2, d=4, c=2)
        analysis = _compute_suit_analysis(hand)
        rng = random.Random(42)

        matched, _, _ = _match_subprofile(
            analysis=analysis,
            seat="N",
            sub=sub,  # type: ignore[arg-type]
            random_suit_choices={"W": ["H"]},
            rng=rng,
            rs_allowed_suits={"W": ["S", "H", "D"]},
        )
        assert matched is True

    def test_three_allowed_suits_non_chosen_is_ordered(self) -> None:
        """RS pick 1 from [S, H, D], S chosen → non-chosen = [H, D], target H."""
        oc = OpponentContingentSuitData(
            opponent_seat="W",
            suit_range=SuitRange(min_cards=5, max_cards=6, min_hcp=0, max_hcp=37),
            use_non_chosen_suit=True,
        )
        sub = FakeSubProfile(opponents_contingent_suit_constraint=oc)
        # North has 5 hearts (H is first non-chosen after S removed) → should match
        hand = _hand_with_suit_lengths(s=2, h=5, d=3, c=3)
        analysis = _compute_suit_analysis(hand)
        rng = random.Random(42)

        matched, _, _ = _match_subprofile(
            analysis=analysis,
            seat="N",
            sub=sub,  # type: ignore[arg-type]
            random_suit_choices={"W": ["S"]},
            rng=rng,
            rs_allowed_suits={"W": ["S", "H", "D"]},
        )
        assert matched is True

    def test_hcp_too_high_on_non_chosen_suit_fails(self) -> None:
        """Non-chosen suit has enough cards but HCP exceeds max → fail."""
        oc = OpponentContingentSuitData(
            opponent_seat="W",
            suit_range=SuitRange(min_cards=5, max_cards=6, min_hcp=0, max_hcp=3),
            use_non_chosen_suit=True,
        )
        sub = FakeSubProfile(opponents_contingent_suit_constraint=oc)
        # North has 5 spades: A K Q J 3 → spade HCP = 4+3+2+1 = 10 (way over max 3)
        hand = ["AS", "KS", "QS", "JS", "3S", "2H", "3H", "4D", "5D", "6C", "7C", "8C", "9C"]
        analysis = _compute_suit_analysis(hand)
        rng = random.Random(42)

        matched, _, _ = _match_subprofile(
            analysis=analysis,
            seat="N",
            sub=sub,  # type: ignore[arg-type]
            random_suit_choices={"W": ["H"]},
            rng=rng,
            rs_allowed_suits={"W": ["S", "H"]},
        )
        assert matched is False

    def test_hcp_too_low_on_non_chosen_suit_fails(self) -> None:
        """Non-chosen suit has enough cards but HCP below min → fail."""
        oc = OpponentContingentSuitData(
            opponent_seat="W",
            suit_range=SuitRange(min_cards=5, max_cards=6, min_hcp=8, max_hcp=12),
            use_non_chosen_suit=True,
        )
        sub = FakeSubProfile(opponents_contingent_suit_constraint=oc)
        # North has 5 spades: 9 8 7 6 5 → spade HCP = 0 (below min 8)
        hand = ["9S", "8S", "7S", "6S", "5S", "AH", "KH", "QH", "AD", "KD", "AC", "KC", "QC"]
        analysis = _compute_suit_analysis(hand)
        rng = random.Random(42)

        matched, _, _ = _match_subprofile(
            analysis=analysis,
            seat="N",
            sub=sub,  # type: ignore[arg-type]
            random_suit_choices={"W": ["H"]},
            rng=rng,
            rs_allowed_suits={"W": ["S", "H"]},
        )
        assert matched is False


class TestOcMixedModes:
    def test_standard_and_non_chosen_oc_in_same_generation(self, tmp_path) -> None:
        """
        Two OC seats in one profile: North uses standard OC (targets chosen),
        South uses non-chosen OC (targets inverse). Both should work together.
        """
        from bridge_engine.hand_profile_model import (
            HandProfile,
            SeatProfile,
            SubProfile,
        )
        from bridge_engine.deal_generator import generate_deals
        from bridge_engine.setup_env import run_setup

        # W: RS pick 1 from [S, H], 6 cards
        w_sub = SubProfile(
            standard=_make_standard(),
            random_suit_constraint=RandomSuitConstraintData(
                required_suits_count=1,
                allowed_suits=["S", "H"],
                suit_ranges=[SuitRange(min_cards=6, max_cards=6, min_hcp=0, max_hcp=37)],
                pair_overrides=[],
            ),
        )
        # N: standard OC — targets W's CHOSEN suit, needs 3+ cards
        n_sub = SubProfile(
            standard=_make_standard(),
            opponents_contingent_suit_constraint=OpponentContingentSuitData(
                opponent_seat="W",
                suit_range=SuitRange(min_cards=3, max_cards=13, min_hcp=0, max_hcp=37),
                use_non_chosen_suit=False,
            ),
        )
        # S: non-chosen OC — targets W's NON-CHOSEN suit, needs 4+ cards
        s_sub = SubProfile(
            standard=_make_standard(),
            opponents_contingent_suit_constraint=OpponentContingentSuitData(
                opponent_seat="W",
                suit_range=SuitRange(min_cards=4, max_cards=13, min_hcp=0, max_hcp=37),
                use_non_chosen_suit=True,
            ),
        )
        e_sub = SubProfile(standard=_make_standard())

        profile = HandProfile(
            profile_name="Test_OC_Mixed_Modes",
            description="Test",
            tag="Overcaller",
            seat_profiles={
                "N": SeatProfile(seat="N", subprofiles=[n_sub]),
                "E": SeatProfile(seat="E", subprofiles=[e_sub]),
                "S": SeatProfile(seat="S", subprofiles=[s_sub]),
                "W": SeatProfile(seat="W", subprofiles=[w_sub]),
            },
            hand_dealing_order=["W", "N", "E", "S"],
            dealer="N",
        )

        setup = run_setup(
            base_dir=tmp_path / "out",
            owner="TestOwner",
            profile_name=profile.profile_name,
            ask_seed_choice=False,
        )
        deal_set = generate_deals(setup, profile, num_deals=5, enable_rotation=False)
        assert len(deal_set.deals) == 5

        for deal in deal_set.deals:
            w_hand = deal.hands["W"]
            n_hand = deal.hands["N"]
            s_hand = deal.hands["S"]

            # Determine W's chosen suit (6 cards in S or H)
            w_analysis = _compute_suit_analysis(w_hand)
            w_chosen = None
            for suit in ["S", "H"]:
                if suit in w_analysis.cards_by_suit and len(w_analysis.cards_by_suit[suit]) == 6:
                    w_chosen = suit
                    break
            assert w_chosen is not None, f"W should have 6 cards in S or H: {w_hand}"

            non_chosen = "H" if w_chosen == "S" else "S"

            # N (standard OC): 3+ cards in W's CHOSEN suit
            n_analysis = _compute_suit_analysis(n_hand)
            n_chosen_count = len(n_analysis.cards_by_suit.get(w_chosen, []))
            assert n_chosen_count >= 3, (
                f"Board {deal.board_number}: N should have 3+ {w_chosen} but has {n_chosen_count}"
            )

            # S (non-chosen OC): 4+ cards in W's NON-CHOSEN suit
            s_analysis = _compute_suit_analysis(s_hand)
            s_non_chosen_count = len(s_analysis.cards_by_suit.get(non_chosen, []))
            assert s_non_chosen_count >= 4, (
                f"Board {deal.board_number}: S should have 4+ {non_chosen} but has {s_non_chosen_count}"
            )
