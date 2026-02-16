# tests/test_profile_viability_extended.py

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import pytest

Suit = str  # "S", "H", "D", "C"

MAX_DECK_HCP = 37  # standard 37 HCP in the full deck


# ---------------------------------------------------------------------------
# Tiny toy model just for these tests
# ---------------------------------------------------------------------------


@dataclass
class SubProfile:
    """
    Minimal subprofile model for viability tests.

    These fields are deliberately simple and do *not* depend on the real
    bridge_engine.profiles definitions – this module is a pure spec harness.
    """

    min_hcp: int
    max_hcp: int
    min_suit_counts: Dict[Suit, int]
    max_suit_counts: Dict[Suit, int]
    random_suit_constraint: Optional[object] = None
    partner_contingent_constraint: Optional[object] = None
    opponents_contingent_suit_constraint: Optional[object] = None


@dataclass
class SeatProfile:
    subprofiles: List[SubProfile]


@dataclass
class HandProfile:
    """
    Toy hand-profile used only for viability spec tests.
    """

    dealer: str
    hand_dealing_order: List[str]
    seat_profiles: Dict[str, SeatProfile]
    profile_name: str = "toy_profile"
    description: str = ""
    tag: str = ""


# ---------------------------------------------------------------------------
# Viability helpers (spec-level)
# ---------------------------------------------------------------------------


def _subprofile_is_viable(sub: SubProfile) -> bool:
    """
    Basic seat-level viability rule:

      * 0 <= min_hcp <= max_hcp <= 37 (deck HCP).
      * Sum of suit minima <= 13.
      * Per-suit min <= per-suit max.

    Random-Suit / PC / OC flags do not, by themselves, make a subprofile
    non-viable.
    """
    # HCP window must be sane and within deck bounds.
    if sub.min_hcp < 0:
        return False
    if sub.max_hcp > MAX_DECK_HCP:
        return False
    if sub.min_hcp > sub.max_hcp:
        return False

    # Suit minima must be achievable in a 13-card hand.
    total_min_suits = sum(sub.min_suit_counts.values())
    if total_min_suits > 13:
        return False

    # Per-suit minima must not exceed per-suit maxima.
    for suit in ("S", "H", "D", "C"):
        mn = sub.min_suit_counts.get(suit, 0)
        mx = sub.max_suit_counts.get(suit, 13)
        if mn > mx:
            return False

    return True


def _ns_pair_jointly_viable(n: SubProfile, s: SubProfile) -> bool:
    """
    Simple NS-coupling viability:

      * For every suit, N.min + S.min <= 13.
      * Combined min HCP for the two seats <= 37.
    """
    # Suit minima combined must not exceed suit capacity in a single hand.
    for suit in ("S", "H", "D", "C"):
        total_min = n.min_suit_counts.get(suit, 0) + s.min_suit_counts.get(suit, 0)
        if total_min > 13:
            return False

    # Total minimum HCP for the NS pair must not exceed the deck total.
    total_min_hcp = n.min_hcp + s.min_hcp
    if total_min_hcp > MAX_DECK_HCP:
        return False

    return True


def validate_profile_viability(profile: HandProfile) -> None:
    """
    Spec-level profile viability:

      * Every constrained seat must have at least one individually-viable
        subprofile.
      * For NS index-coupling (same-length subprofile arrays), there must be
        at least one index i where N[i] and S[i] are jointly viable.
    """
    # Seat-level check: at least one viable subprofile per constrained seat.
    for seat, seat_profile in profile.seat_profiles.items():
        if not seat_profile.subprofiles:
            # Unconstrained seat – always viable.
            continue

        viable_any = any(_subprofile_is_viable(sp) for sp in seat_profile.subprofiles)
        if not viable_any:
            raise ValueError(f"No viable subprofiles for seat {seat!r}")

    # NS coupling check (very simplified spec version).
    north = profile.seat_profiles.get("N")
    south = profile.seat_profiles.get("S")

    if north is None or south is None:
        return

    n_subs = north.subprofiles
    s_subs = south.subprofiles

    if len(n_subs) != len(s_subs):
        # For this spec, we only consider the "equal-length" coupling case.
        return

    if len(n_subs) <= 1:
        # Nothing special to check: 0/1 subprofile per seat.
        return

    # There must be at least one index i where both subprofiles are individually
    # viable and jointly viable under NS-coupling, and there must NOT be any
    # index where both are individually viable but jointly impossible.
    jointly_viable_found = False

    for n_sub, s_sub in zip(n_subs, s_subs):
        n_ok = _subprofile_is_viable(n_sub)
        s_ok = _subprofile_is_viable(s_sub)

        if not (n_ok and s_ok):
            # If one side is individually impossible, we don't care about their
            # joint feasibility at this index.
            continue

        if not _ns_pair_jointly_viable(n_sub, s_sub):
            # Both individually viable, but jointly impossible at this index:
            # NS index-coupling could pick this pair, so reject the profile.
            raise ValueError("NS index-coupled pair impossible at some index")

        jointly_viable_found = True

    if not jointly_viable_found:
        # No index with both individually-viable and jointly-viable subprofiles.
        raise ValueError("No NS index-coupled subprofile pair is jointly viable")


# ---------------------------------------------------------------------------
# Unit tests – seat-level viability
# ---------------------------------------------------------------------------


def test_subprofile_is_viable_trivially_standard() -> None:
    """
    A subprofile with very loose, standard constraints should be viable.
    Example: 10–16 HCP, any shape.
    """
    sub = SubProfile(
        min_hcp=10,
        max_hcp=16,
        min_suit_counts={"S": 0, "H": 0, "D": 0, "C": 0},
        max_suit_counts={"S": 13, "H": 13, "D": 13, "C": 13},
        random_suit_constraint=None,
        partner_contingent_constraint=None,
        opponents_contingent_suit_constraint=None,
    )
    assert _subprofile_is_viable(sub)


def test_subprofile_is_not_viable_impossible_hcp_window() -> None:
    """
    A subprofile with an impossible HCP window must be rejected.
    Example: min_hcp > 37 (more than the whole deck).
    """
    sub = SubProfile(
        min_hcp=38,
        max_hcp=40,
        min_suit_counts={"S": 0, "H": 0, "D": 0, "C": 0},
        max_suit_counts={"S": 13, "H": 13, "D": 13, "C": 13},
        random_suit_constraint=None,
        partner_contingent_constraint=None,
        opponents_contingent_suit_constraint=None,
    )
    assert not _subprofile_is_viable(sub)


def test_subprofile_is_not_viable_suit_minima_over_13() -> None:
    """
    Sum of required suit cards > 13 makes the seat impossible.
    """
    sub = SubProfile(
        min_hcp=0,
        max_hcp=37,
        min_suit_counts={"S": 4, "H": 4, "D": 4, "C": 4},  # 16 > 13
        max_suit_counts={"S": 13, "H": 13, "D": 13, "C": 13},
        random_suit_constraint=None,
        partner_contingent_constraint=None,
        opponents_contingent_suit_constraint=None,
    )
    assert not _subprofile_is_viable(sub)


def test_subprofile_is_viable_tight_but_consistent_suit_minima() -> None:
    """
    Edge case where suit minima sum exactly to 13 should still be viable.
    """
    sub = SubProfile(
        min_hcp=0,
        max_hcp=37,
        min_suit_counts={"S": 5, "H": 4, "D": 3, "C": 1},  # sum == 13
        max_suit_counts={"S": 13, "H": 13, "D": 13, "C": 13},
        random_suit_constraint=None,
        partner_contingent_constraint=None,
        opponents_contingent_suit_constraint=None,
    )
    assert _subprofile_is_viable(sub)


def test_subprofile_is_viable_random_suit_basic_window() -> None:
    """
    Random-Suit subprofile with sane parameters must be viable.
    """
    sub = SubProfile(
        min_hcp=8,
        max_hcp=14,
        min_suit_counts={"S": 0, "H": 0, "D": 0, "C": 0},
        max_suit_counts={"S": 13, "H": 13, "D": 13, "C": 13},
        random_suit_constraint=object(),  # RS flag present
        partner_contingent_constraint=None,
        opponents_contingent_suit_constraint=None,
    )
    assert _subprofile_is_viable(sub)


def test_subprofile_is_not_viable_random_suit_impossible_shape() -> None:
    """
    RS plus impossible shape must still be considered non-viable.
    """
    sub = SubProfile(
        min_hcp=0,
        max_hcp=37,
        min_suit_counts={"S": 7, "H": 7, "D": 0, "C": 0},  # 14 > 13
        max_suit_counts={"S": 13, "H": 13, "D": 13, "C": 13},
        random_suit_constraint=object(),
        partner_contingent_constraint=None,
        opponents_contingent_suit_constraint=None,
    )
    assert not _subprofile_is_viable(sub)


# ---------------------------------------------------------------------------
# Unit tests – profile-level viability
# ---------------------------------------------------------------------------


def test_validate_profile_viability_simple_ns_profile_ok() -> None:
    """
    Two NS subprofiles that are individually viable and jointly viable
    under coupling should pass validate_profile_viability.
    """
    # Subprofile index 0 – loose, clearly viable.
    n0 = SubProfile(
        min_hcp=8,
        max_hcp=16,
        min_suit_counts={"S": 4, "H": 2, "D": 2, "C": 1},
        max_suit_counts={"S": 13, "H": 13, "D": 13, "C": 13},
    )
    s0 = SubProfile(
        min_hcp=8,
        max_hcp=16,
        min_suit_counts={"S": 1, "H": 4, "D": 2, "C": 2},
        max_suit_counts={"S": 13, "H": 13, "D": 13, "C": 13},
    )

    # Index 1 – also viable and jointly OK.
    n1 = SubProfile(
        min_hcp=0,
        max_hcp=37,
        min_suit_counts={"S": 5, "H": 3, "D": 3, "C": 2},
        max_suit_counts={"S": 13, "H": 13, "D": 13, "C": 13},
    )
    s1 = SubProfile(
        min_hcp=0,
        max_hcp=37,
        min_suit_counts={"S": 2, "H": 5, "D": 3, "C": 3},
        max_suit_counts={"S": 13, "H": 13, "D": 13, "C": 13},
    )

    profile = HandProfile(
        dealer="N",
        hand_dealing_order=["N", "E", "S", "W"],
        seat_profiles={
            "N": SeatProfile(subprofiles=[n0, n1]),
            "S": SeatProfile(subprofiles=[s0, s1]),
        },
    )

    # Should not raise.
    validate_profile_viability(profile)


def test_validate_profile_viability_rejects_impossible_ns_coupling() -> None:
    """
    If NS index-coupling *forces* us into an impossible combination of
    subprofiles (e.g. N index 1 and S index 1 together cannot exist),
    validate_profile_viability must reject the profile.
    """
    # Subprofile 0: individually viable and jointly fine.
    n0 = SubProfile(
        min_hcp=0,
        max_hcp=37,
        min_suit_counts={"S": 4, "H": 3, "D": 3, "C": 3},
        max_suit_counts={"S": 13, "H": 13, "D": 13, "C": 13},
    )
    s0 = SubProfile(
        min_hcp=0,
        max_hcp=37,
        min_suit_counts={"S": 3, "H": 4, "D": 3, "C": 3},
        max_suit_counts={"S": 13, "H": 13, "D": 13, "C": 13},
    )

    # Subprofile 1: designed so N(1) + S(1) is impossible
    # (combined S minima > 13).
    n1 = SubProfile(
        min_hcp=0,
        max_hcp=37,
        min_suit_counts={"S": 10, "H": 3, "D": 0, "C": 0},
        max_suit_counts={"S": 13, "H": 13, "D": 13, "C": 13},
    )
    s1 = SubProfile(
        min_hcp=0,
        max_hcp=37,
        min_suit_counts={"S": 4, "H": 4, "D": 0, "C": 0},  # 10 + 4 = 14 > 13
        max_suit_counts={"S": 13, "H": 13, "D": 13, "C": 13},
    )

    profile = HandProfile(
        dealer="N",
        hand_dealing_order=["N", "E", "S", "W"],
        seat_profiles={
            "N": SeatProfile(subprofiles=[n0, n1]),
            "S": SeatProfile(subprofiles=[s0, s1]),
        },
    )

    with pytest.raises(ValueError):
        validate_profile_viability(profile)


def test_validate_profile_viability_unconstrained_profile_always_ok() -> None:
    """
    A profile with no seat constraints should always be considered viable.
    """
    profile = HandProfile(
        dealer="N",
        hand_dealing_order=["N", "E", "S", "W"],
        seat_profiles={},  # no constrained seats
    )

    # Should not raise.
    validate_profile_viability(profile)


def test_validate_profile_viability_rejects_profile_with_no_viable_subprofiles() -> None:
    """
    If a seat has subprofiles and every one of them is individually impossible,
    the profile must be rejected.
    """
    impossible_sub = SubProfile(
        min_hcp=50,  # impossible given MAX_DECK_HCP = 37
        max_hcp=60,
        min_suit_counts={"S": 0, "H": 0, "D": 0, "C": 0},
        max_suit_counts={"S": 13, "H": 13, "D": 13, "C": 13},
        random_suit_constraint=None,
        partner_contingent_constraint=None,
        opponents_contingent_suit_constraint=None,
    )

    profile = HandProfile(
        dealer="N",
        hand_dealing_order=["N", "E", "S", "W"],
        seat_profiles={
            "N": SeatProfile(subprofiles=[impossible_sub]),
        },
    )

    with pytest.raises(ValueError):
        validate_profile_viability(profile)
