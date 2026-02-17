# tests/test_pc_non_chosen_suit.py
"""
Tests for the PC non-chosen-suit feature.

When use_non_chosen_suit=True on a PartnerContingentData, the PC
matching targets the suit the partner did NOT choose (the inverse of
the normal behaviour which targets the first chosen suit).
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pytest

from bridge_engine.hand_profile_model import (
    PartnerContingentData,
    RandomSuitConstraintData,
    StandardSuitConstraints,
    SuitRange,
)
from bridge_engine.seat_viability import (
    SuitAnalysis,
    _compute_suit_analysis,
    _match_partner_contingent,
    _match_subprofile,
)


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
    partner_contingent_constraint: Optional[PartnerContingentData] = None
    opponents_contingent_suit_constraint: Optional[Any] = None
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


class TestPcDataModelRoundTrip:
    def test_to_dict_includes_use_non_chosen_suit_true(self) -> None:
        pc = PartnerContingentData(
            partner_seat="N",
            suit_range=SuitRange(min_cards=3, max_cards=4, min_hcp=0, max_hcp=10),
            use_non_chosen_suit=True,
        )
        d = pc.to_dict()
        assert d["use_non_chosen_suit"] is True
        assert d["partner_seat"] == "N"

    def test_to_dict_includes_use_non_chosen_suit_false(self) -> None:
        pc = PartnerContingentData(
            partner_seat="S",
            suit_range=SuitRange(),
        )
        d = pc.to_dict()
        assert d["use_non_chosen_suit"] is False

    def test_from_dict_with_flag_true(self) -> None:
        data = {
            "partner_seat": "N",
            "suit_range": {"min_cards": 3, "max_cards": 4, "min_hcp": 0, "max_hcp": 10},
            "use_non_chosen_suit": True,
        }
        pc = PartnerContingentData.from_dict(data)
        assert pc.use_non_chosen_suit is True
        assert pc.partner_seat == "N"
        assert pc.suit_range.min_cards == 3

    def test_from_dict_backward_compat_missing_key(self) -> None:
        """Old JSON without use_non_chosen_suit should default to False."""
        data = {
            "partner_seat": "S",
            "suit_range": {"min_cards": 0, "max_cards": 13},
        }
        pc = PartnerContingentData.from_dict(data)
        assert pc.use_non_chosen_suit is False

    def test_round_trip(self) -> None:
        pc = PartnerContingentData(
            partner_seat="N",
            suit_range=SuitRange(min_cards=3, max_cards=4, min_hcp=0, max_hcp=10),
            use_non_chosen_suit=True,
        )
        restored = PartnerContingentData.from_dict(pc.to_dict())
        assert restored == pc


# ---------------------------------------------------------------------------
# 2. PC matching — standard (regression)
# ---------------------------------------------------------------------------


class TestPcStandardRegression:
    """Ensure standard PC (use_non_chosen_suit=False) still works."""

    def test_standard_pc_matches_chosen_suit(self) -> None:
        """PC targets N's first chosen suit (H). S has 4H → should match."""
        pc = PartnerContingentData(
            partner_seat="N",
            suit_range=SuitRange(min_cards=3, max_cards=5, min_hcp=0, max_hcp=37),
            use_non_chosen_suit=False,
        )
        hand = _hand_with_suit_lengths(s=3, h=4, d=3, c=3)
        analysis = _compute_suit_analysis(hand)

        assert _match_partner_contingent(analysis, pc, ["H"]) is True

    def test_standard_pc_fails_when_chosen_suit_too_short(self) -> None:
        """PC targets N's first chosen suit (H). S has 1H → should fail."""
        pc = PartnerContingentData(
            partner_seat="N",
            suit_range=SuitRange(min_cards=3, max_cards=5, min_hcp=0, max_hcp=37),
            use_non_chosen_suit=False,
        )
        hand = _hand_with_suit_lengths(s=5, h=1, d=4, c=3)
        analysis = _compute_suit_analysis(hand)

        assert _match_partner_contingent(analysis, pc, ["H"]) is False


# ---------------------------------------------------------------------------
# 3. PC matching — non-chosen suit
# ---------------------------------------------------------------------------


class TestPcNonChosenSuit:
    def test_partner_picks_h_targets_s(self) -> None:
        """N RS picks H from [S,H] → S PC non-chosen targets S."""
        pc = PartnerContingentData(
            partner_seat="N",
            suit_range=SuitRange(min_cards=4, max_cards=6, min_hcp=0, max_hcp=37),
            use_non_chosen_suit=True,
        )
        # South has 4 spades (the non-chosen suit) → should match
        hand = _hand_with_suit_lengths(s=4, h=3, d=3, c=3)
        analysis = _compute_suit_analysis(hand)

        matched = _match_partner_contingent(analysis, pc, ["H"], rs_allowed_suits={"N": ["S", "H"]})
        assert matched is True

    def test_partner_picks_s_targets_h(self) -> None:
        """N RS picks S from [S,H] → S PC non-chosen targets H."""
        pc = PartnerContingentData(
            partner_seat="N",
            suit_range=SuitRange(min_cards=4, max_cards=6, min_hcp=0, max_hcp=37),
            use_non_chosen_suit=True,
        )
        # South has 5 hearts (the non-chosen suit) → should match
        hand = _hand_with_suit_lengths(s=2, h=5, d=3, c=3)
        analysis = _compute_suit_analysis(hand)

        matched = _match_partner_contingent(analysis, pc, ["S"], rs_allowed_suits={"N": ["S", "H"]})
        assert matched is True

    def test_non_chosen_fails_when_suit_too_short(self) -> None:
        """N picks H → target is S, but S only has 1S → fail."""
        pc = PartnerContingentData(
            partner_seat="N",
            suit_range=SuitRange(min_cards=4, max_cards=6, min_hcp=0, max_hcp=37),
            use_non_chosen_suit=True,
        )
        hand = _hand_with_suit_lengths(s=1, h=5, d=4, c=3)
        analysis = _compute_suit_analysis(hand)

        matched = _match_partner_contingent(analysis, pc, ["H"], rs_allowed_suits={"N": ["S", "H"]})
        assert matched is False

    def test_non_chosen_with_hcp_constraint(self) -> None:
        """N picks H → target is S. S has 4S with 0-5 HCP check."""
        pc = PartnerContingentData(
            partner_seat="N",
            suit_range=SuitRange(min_cards=3, max_cards=5, min_hcp=0, max_hcp=5),
            use_non_chosen_suit=True,
        )
        # Hand: 9S 8S 7S 6S ... → spade HCP = 0 (within 0-5)
        hand = ["9S", "8S", "7S", "6S", "AH", "KH", "QH", "AD", "KD", "AC", "KC", "QC", "JC"]
        analysis = _compute_suit_analysis(hand)

        matched = _match_partner_contingent(analysis, pc, ["H"], rs_allowed_suits={"N": ["S", "H"]})
        assert matched is True

    def test_hcp_too_high_on_non_chosen_suit_fails(self) -> None:
        """N picks H → target is S. S has 4S with HCP too high → fail."""
        pc = PartnerContingentData(
            partner_seat="N",
            suit_range=SuitRange(min_cards=3, max_cards=5, min_hcp=0, max_hcp=3),
            use_non_chosen_suit=True,
        )
        # Hand: AS KS QS JS ... → spade HCP = 4+3+2+1 = 10 (over max 3)
        hand = ["AS", "KS", "QS", "JS", "2H", "3H", "4D", "5D", "6C", "7C", "8C", "9C", "TC"]
        analysis = _compute_suit_analysis(hand)

        matched = _match_partner_contingent(analysis, pc, ["H"], rs_allowed_suits={"N": ["S", "H"]})
        assert matched is False


# ---------------------------------------------------------------------------
# 4. Graceful failure
# ---------------------------------------------------------------------------


class TestPcNonChosenGracefulFail:
    def test_no_rs_allowed_suits_returns_false(self) -> None:
        """When rs_allowed_suits is None, non-chosen PC fails gracefully."""
        pc = PartnerContingentData(
            partner_seat="N",
            suit_range=SuitRange(min_cards=4, max_cards=6, min_hcp=0, max_hcp=37),
            use_non_chosen_suit=True,
        )
        hand = _hand_with_suit_lengths(s=5, h=3, d=3, c=2)
        analysis = _compute_suit_analysis(hand)

        matched = _match_partner_contingent(analysis, pc, ["H"], rs_allowed_suits=None)
        assert matched is False

    def test_all_suits_chosen_returns_false(self) -> None:
        """When partner chose all allowed suits, non-chosen is empty → fail."""
        pc = PartnerContingentData(
            partner_seat="N",
            suit_range=SuitRange(min_cards=3, max_cards=6, min_hcp=0, max_hcp=37),
            use_non_chosen_suit=True,
        )
        hand = _hand_with_suit_lengths(s=5, h=5, d=2, c=1)
        analysis = _compute_suit_analysis(hand)

        # N chose both S and H from allowed [S, H] — no non-chosen suits
        matched = _match_partner_contingent(analysis, pc, ["S", "H"], rs_allowed_suits={"N": ["S", "H"]})
        assert matched is False


# ---------------------------------------------------------------------------
# 5. Validation
# ---------------------------------------------------------------------------


class TestPcNonChosenValidation:
    def test_validation_passes_with_exactly_one_non_chosen(self) -> None:
        """No error when partner has RS with exactly 1 non-chosen suit."""
        from bridge_engine.hand_profile_model import (
            HandProfile,
            SeatProfile,
            SubProfile,
        )
        from bridge_engine.hand_profile_validate import validate_profile

        # N has RS: pick 1 from [S, H] — exactly 1 non-chosen
        n_sub = SubProfile(
            standard=_make_standard(),
            random_suit_constraint=RandomSuitConstraintData(
                required_suits_count=1,
                allowed_suits=["S", "H"],
                suit_ranges=[SuitRange(min_cards=5, max_cards=6)],
                pair_overrides=[],
            ),
        )
        # S has PC non-chosen targeting N
        s_sub = SubProfile(
            standard=_make_standard(),
            partner_contingent_constraint=PartnerContingentData(
                partner_seat="N",
                suit_range=SuitRange(min_cards=3, max_cards=4, min_hcp=0, max_hcp=10),
                use_non_chosen_suit=True,
            ),
        )
        e_sub = SubProfile(standard=_make_standard())
        w_sub = SubProfile(standard=_make_standard())

        profile = HandProfile(
            profile_name="Test_PC_NonChosen",
            description="Test",
            tag="Opener",
            seat_profiles={
                "N": SeatProfile(seat="N", subprofiles=[n_sub]),
                "E": SeatProfile(seat="E", subprofiles=[e_sub]),
                "S": SeatProfile(seat="S", subprofiles=[s_sub]),
                "W": SeatProfile(seat="W", subprofiles=[w_sub]),
            },
            hand_dealing_order=["N", "S", "E", "W"],
            dealer="N",
        )
        result = validate_profile(profile.to_dict())
        assert result is not None

    def test_validation_fails_no_surplus_rs(self) -> None:
        """Error when partner RS has required == allowed (no non-chosen)."""
        from bridge_engine.hand_profile_model import (
            HandProfile,
            SeatProfile,
            SubProfile,
            ProfileError,
        )
        from bridge_engine.hand_profile_validate import validate_profile

        # N has RS: pick 2 from [S, H] — 0 non-chosen
        n_sub = SubProfile(
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
        s_sub = SubProfile(
            standard=_make_standard(),
            partner_contingent_constraint=PartnerContingentData(
                partner_seat="N",
                suit_range=SuitRange(min_cards=3, max_cards=4),
                use_non_chosen_suit=True,
            ),
        )
        e_sub = SubProfile(standard=_make_standard())
        w_sub = SubProfile(standard=_make_standard())

        profile = HandProfile(
            profile_name="Test_PC_NoSurplus",
            description="Test",
            tag="Opener",
            seat_profiles={
                "N": SeatProfile(seat="N", subprofiles=[n_sub]),
                "E": SeatProfile(seat="E", subprofiles=[e_sub]),
                "S": SeatProfile(seat="S", subprofiles=[s_sub]),
                "W": SeatProfile(seat="W", subprofiles=[w_sub]),
            },
            hand_dealing_order=["N", "S", "E", "W"],
            dealer="N",
        )
        with pytest.raises(ProfileError, match="non-chosen-suit PC"):
            validate_profile(profile.to_dict())

    def test_validation_fails_multiple_non_chosen(self) -> None:
        """Error when partner RS has 2+ non-chosen suits."""
        from bridge_engine.hand_profile_model import (
            HandProfile,
            SeatProfile,
            SubProfile,
            ProfileError,
        )
        from bridge_engine.hand_profile_validate import validate_profile

        # N has RS: pick 1 from [S, H, D] — 2 non-chosen (not exactly 1)
        n_sub = SubProfile(
            standard=_make_standard(),
            random_suit_constraint=RandomSuitConstraintData(
                required_suits_count=1,
                allowed_suits=["S", "H", "D"],
                suit_ranges=[SuitRange(min_cards=6, max_cards=6)],
                pair_overrides=[],
            ),
        )
        s_sub = SubProfile(
            standard=_make_standard(),
            partner_contingent_constraint=PartnerContingentData(
                partner_seat="N",
                suit_range=SuitRange(min_cards=4, max_cards=5),
                use_non_chosen_suit=True,
            ),
        )
        e_sub = SubProfile(standard=_make_standard())
        w_sub = SubProfile(standard=_make_standard())

        profile = HandProfile(
            profile_name="Test_PC_MultiNonChosen",
            description="Test",
            tag="Opener",
            seat_profiles={
                "N": SeatProfile(seat="N", subprofiles=[n_sub]),
                "E": SeatProfile(seat="E", subprofiles=[e_sub]),
                "S": SeatProfile(seat="S", subprofiles=[s_sub]),
                "W": SeatProfile(seat="W", subprofiles=[w_sub]),
            },
            hand_dealing_order=["N", "S", "E", "W"],
            dealer="N",
        )
        with pytest.raises(ProfileError, match="exactly 1 non-chosen suit"):
            validate_profile(profile.to_dict())


# ---------------------------------------------------------------------------
# 6. Integration — full deal generation
# ---------------------------------------------------------------------------


class TestPcNonChosenIntegration:
    def test_generate_deals_with_non_chosen_pc(self, tmp_path) -> None:
        """
        End-to-end: N RS picks 1 from [S,H], S PC non-chosen gets the
        other suit with 3-5 cards. Generate 5 boards and verify.
        """
        from bridge_engine.hand_profile_model import (
            HandProfile,
            SeatProfile,
            SubProfile,
        )
        from bridge_engine.deal_generator import generate_deals
        from bridge_engine.setup_env import run_setup

        # N: RS pick 1 from [S, H], 6 cards in chosen suit
        n_sub = SubProfile(
            standard=_make_standard(),
            random_suit_constraint=RandomSuitConstraintData(
                required_suits_count=1,
                allowed_suits=["S", "H"],
                suit_ranges=[SuitRange(min_cards=6, max_cards=6, min_hcp=0, max_hcp=37)],
                pair_overrides=[],
            ),
        )
        # S: PC non-chosen targeting N, 3-5 cards in the non-chosen suit
        s_sub = SubProfile(
            standard=_make_standard(),
            partner_contingent_constraint=PartnerContingentData(
                partner_seat="N",
                suit_range=SuitRange(min_cards=3, max_cards=5, min_hcp=0, max_hcp=37),
                use_non_chosen_suit=True,
            ),
        )
        e_sub = SubProfile(standard=_make_standard())
        w_sub = SubProfile(standard=_make_standard())

        profile = HandProfile(
            profile_name="Test_PC_NonChosen_E2E",
            description="Test",
            tag="Opener",
            seat_profiles={
                "N": SeatProfile(seat="N", subprofiles=[n_sub]),
                "E": SeatProfile(seat="E", subprofiles=[e_sub]),
                "S": SeatProfile(seat="S", subprofiles=[s_sub]),
                "W": SeatProfile(seat="W", subprofiles=[w_sub]),
            },
            hand_dealing_order=["N", "S", "E", "W"],
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
            n_hand = deal.hands["N"]
            s_hand = deal.hands["S"]

            # Determine which suit N chose (the one with 6 cards)
            n_analysis = _compute_suit_analysis(n_hand)
            n_chosen = None
            for suit in ["S", "H"]:
                if suit in n_analysis.cards_by_suit and len(n_analysis.cards_by_suit[suit]) == 6:
                    n_chosen = suit
                    break
            assert n_chosen is not None, f"N should have exactly 6 cards in S or H: {n_hand}"

            # The non-chosen suit
            non_chosen = "H" if n_chosen == "S" else "S"

            # S should have 3-5 cards in the non-chosen suit
            s_analysis = _compute_suit_analysis(s_hand)
            s_count = len(s_analysis.cards_by_suit.get(non_chosen, []))
            assert 3 <= s_count <= 5, (
                f"Board {deal.board_number}: N chose {n_chosen}, S should have 3-5 {non_chosen} but has {s_count}"
            )
