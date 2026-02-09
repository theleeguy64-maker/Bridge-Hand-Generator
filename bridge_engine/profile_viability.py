"""
Extended profile-level viability helpers.

Historically these lived in a `profile_viability` module. The current
per-seat implementation lives in `seat_viability`. This module:

  * re-exports `_subprofile_is_viable` for backwards compatibility, and
  * provides a profile-level `validate_profile_viability(...)` that adds
    NS index-coupling checks on top of the lighter per-seat validation.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import warnings
from types import SimpleNamespace

from .hand_profile_model import ProfileError
from .seat_viability import (
    _subprofile_is_viable,
    _subprofile_is_viable_light,
    validate_profile_viability_light,
)

__all__ = [
    "_subprofile_is_viable",
    "validate_profile_viability",
    "_cross_seat_feasible",
]


def _get_suit_min(sub: Any, suit: str) -> int:
    """
    Extract minimum card count for a suit from a subprofile.

    Supports both:
    - Real SubProfile objects (sub.standard.spades.min_cards, etc.)
    - Toy model objects (sub.min_suit_counts dict)
    """
    # Try real SubProfile structure first
    std = getattr(sub, "standard", None)
    if std is not None:
        suit_map = {"S": "spades", "H": "hearts", "D": "diamonds", "C": "clubs"}
        suit_obj = getattr(std, suit_map.get(suit, ""), None)
        if suit_obj is not None:
            return getattr(suit_obj, "min_cards", 0)

    # Fall back to toy model structure
    min_counts = getattr(sub, "min_suit_counts", {}) or {}
    return min_counts.get(suit, 0)


def _get_suit_max(sub: Any, suit: str) -> int:
    """
    Extract maximum card count for a suit from a subprofile.

    Supports both:
    - Real SubProfile objects (sub.standard.spades.max_cards, etc.)
    - Toy model objects (sub.max_suit_counts dict)

    Defaults to 13 (unconstrained) if not specified.
    """
    std = getattr(sub, "standard", None)
    if std is not None:
        suit_map = {"S": "spades", "H": "hearts", "D": "diamonds", "C": "clubs"}
        suit_obj = getattr(std, suit_map.get(suit, ""), None)
        if suit_obj is not None:
            return getattr(suit_obj, "max_cards", 13)

    max_counts = getattr(sub, "max_suit_counts", {}) or {}
    return max_counts.get(suit, 13)


def _get_total_min_hcp(sub: Any) -> int:
    """
    Extract total_min_hcp from a subprofile.

    Supports real SubProfile (sub.standard.total_min_hcp) and
    toy model objects (sub.min_hcp).  Defaults to 0 (unconstrained).
    """
    std = getattr(sub, "standard", None)
    if std is not None:
        return getattr(std, "total_min_hcp", 0)
    return getattr(sub, "min_hcp", 0)


def _get_total_max_hcp(sub: Any) -> int:
    """
    Extract total_max_hcp from a subprofile.

    Supports real SubProfile (sub.standard.total_max_hcp) and
    toy model objects (sub.max_hcp).  Defaults to 37 (max possible in 13 cards).
    """
    std = getattr(sub, "standard", None)
    if std is not None:
        return getattr(std, "total_max_hcp", 37)
    return getattr(sub, "max_hcp", 37)


# ---------------------------------------------------------------------------
# Cross-seat feasibility
# ---------------------------------------------------------------------------
# The deck has exactly 40 HCP and 13 cards per suit.  If the chosen
# subprofiles across all 4 seats have combined minimums that exceed
# these deck-level limits, the combination can never succeed.

TOTAL_DECK_HCP = 40       # 4 Aces × 4 + 4 Kings × 3 + 4 Queens × 2 + 4 Jacks × 1
CARDS_PER_SUIT = 13       # standard bridge deck


def _cross_seat_feasible(
    chosen_subs: Dict[str, Any],
) -> Tuple[bool, Optional[str]]:
    """
    Check whether a set of chosen subprofiles (one per seat) are jointly
    feasible from an HCP and per-suit card count perspective.

    Three checks:
      1. sum(min_hcp) across all seats must be <= 40  (deck has only 40 HCP)
      2. sum(max_hcp) across all seats must be >= 40  (HCP must go somewhere)
      3. For each suit: sum(min_cards) <= 13, sum(max_cards) >= 13

    Args:
        chosen_subs: Dict mapping seat name -> SubProfile (or compatible object).

    Returns:
        (True, None) if feasible.
        (False, reason_string) if infeasible.
    """
    seats = list(chosen_subs.keys())
    if not seats:
        return True, None

    # Check 1: total HCP minimums must not exceed deck total.
    total_min_hcp = sum(_get_total_min_hcp(chosen_subs[s]) for s in seats)
    if total_min_hcp > TOTAL_DECK_HCP:
        return False, (
            f"sum(min_hcp)={total_min_hcp} > {TOTAL_DECK_HCP}: "
            f"combined HCP minimums exceed deck total"
        )

    # Check 2: total HCP maximums must be able to absorb all deck HCP.
    total_max_hcp = sum(_get_total_max_hcp(chosen_subs[s]) for s in seats)
    if total_max_hcp < TOTAL_DECK_HCP:
        return False, (
            f"sum(max_hcp)={total_max_hcp} < {TOTAL_DECK_HCP}: "
            f"combined HCP maximums can't absorb all deck HCP"
        )

    # Check 3: per-suit card counts.
    for suit in ("S", "H", "D", "C"):
        suit_min_sum = sum(_get_suit_min(chosen_subs[s], suit) for s in seats)
        if suit_min_sum > CARDS_PER_SUIT:
            return False, (
                f"suit {suit}: sum(min_cards)={suit_min_sum} > {CARDS_PER_SUIT}"
            )
        suit_max_sum = sum(_get_suit_max(chosen_subs[s], suit) for s in seats)
        if suit_max_sum < CARDS_PER_SUIT:
            return False, (
                f"suit {suit}: sum(max_cards)={suit_max_sum} < {CARDS_PER_SUIT}"
            )

    return True, None


def _ns_pair_jointly_viable(n_sub: Any, s_sub: Any) -> bool:
    """
    Lightweight joint viability check for an NS index-coupled pair.

    For now we enforce that the combined suit minima don't exceed the deck
    (13 cards per suit). This is enough for the current tests.
    """
    for suit in ("S", "H", "D", "C"):
        n_val = _get_suit_min(n_sub, suit)
        s_val = _get_suit_min(s_sub, suit)
        if n_val + s_val > 13:
            return False

    return True


def _check_cross_seat_subprofile_viability(profile: Any) -> List[str]:
    """
    Detect "dead" subprofiles that can never participate in a feasible
    4-seat combination, even with the most generous subprofiles on all
    other seats.

    For each subprofile on each seat, we compute the best-case scenario:
    the lowest min_hcp, highest max_hcp, lowest min_cards, and highest
    max_cards that any subprofile on each other seat can offer.  If the
    subprofile still can't work under this best case, it is dead.

    Returns:
        List of warning strings for dead subprofiles.

    Raises:
        ProfileError if ALL subprofiles for any seat are dead.
    """
    seat_profiles = getattr(profile, "seat_profiles", None)
    if not isinstance(seat_profiles, Mapping):
        return []

    # Collect all seats and their subprofile lists.
    seat_subs: Dict[str, list] = {}
    for seat, sp in seat_profiles.items():
        subs = getattr(sp, "subprofiles", None)
        if subs:
            seat_subs[seat] = list(subs)

    if len(seat_subs) < 2:
        # Need at least 2 seats for cross-seat checks to matter.
        return []

    all_seats = list(seat_subs.keys())

    # For each seat, precompute the "most generous" values across all
    # subprofiles — these represent the best case for other seats.
    best_min_hcp: Dict[str, int] = {}     # lowest min_hcp on this seat
    best_max_hcp: Dict[str, int] = {}     # highest max_hcp on this seat
    best_suit_min: Dict[str, Dict[str, int]] = {}   # lowest min_cards per suit
    best_suit_max: Dict[str, Dict[str, int]] = {}   # highest max_cards per suit

    for seat, subs in seat_subs.items():
        best_min_hcp[seat] = min(_get_total_min_hcp(s) for s in subs)
        best_max_hcp[seat] = max(_get_total_max_hcp(s) for s in subs)
        best_suit_min[seat] = {}
        best_suit_max[seat] = {}
        for suit in ("S", "H", "D", "C"):
            best_suit_min[seat][suit] = min(_get_suit_min(s, suit) for s in subs)
            best_suit_max[seat][suit] = max(_get_suit_max(s, suit) for s in subs)

    dead_warnings: List[str] = []

    for seat, subs in seat_subs.items():
        other_seats = [s for s in all_seats if s != seat]
        alive_count = 0

        for idx, sub in enumerate(subs):
            # Build best-case combination: this sub + most generous from others.
            test_subs = {seat: sub}
            for other in other_seats:
                # Create a synthetic "best case" sub for each other seat.
                test_subs[other] = SimpleNamespace(
                    standard=None,
                    min_hcp=best_min_hcp[other],
                    max_hcp=best_max_hcp[other],
                    min_suit_counts=best_suit_min[other],
                    max_suit_counts=best_suit_max[other],
                )

            feasible, reason = _cross_seat_feasible(test_subs)
            if feasible:
                alive_count += 1
            else:
                dead_warnings.append(
                    f"Seat {seat} subprofile {idx + 1}: dead "
                    f"(infeasible with best-case other seats: {reason})"
                )

        if alive_count == 0:
            raise ProfileError(
                f"Seat {seat}: ALL {len(subs)} subprofiles are dead — "
                f"no subprofile can work with any combination of other seats. "
                f"Check HCP ranges and suit constraints."
            )

    return dead_warnings


def validate_profile_viability(profile: Any) -> None:
    """
    Extended profile viability:

      1. Run validate_profile_viability_light(...) to enforce per-seat and
         per-subprofile invariants.
      2. If NS index-coupling is enabled and both N/S have >1 subprofiles
         with equal lengths, check that each paired index is jointly viable.
      3. Cross-seat subprofile viability: detect subprofiles that can never
         work with ANY combination of other seats (dead subprofiles).
         Warns for dead subs; raises ProfileError if ALL subs on a seat die.
    """
    # Step 1: baseline light validation (per-seat checks, HCP, shape, etc.).
    validate_profile_viability_light(profile)

    # Step 2: NS index-coupling overlay.
    _validate_ns_coupling(profile)

    # Step 3: cross-seat subprofile viability (dead subprofile detection).
    # Check each subprofile against the best-case from all other seats.
    # Warns for dead subprofiles; raises ProfileError if ALL subs on any
    # seat are dead.
    dead_warnings = _check_cross_seat_subprofile_viability(profile)
    for warning_msg in dead_warnings:
        warnings.warn(warning_msg, stacklevel=2)


def _validate_ns_coupling(profile: Any) -> None:
    """
    NS index-coupling viability check.

    If NS index-coupling is enabled and both N/S have >1 subprofiles
    with equal lengths, then for each index i:
      - If both N[i] and S[i] are individually viable, they must also
        be jointly viable as a pair; otherwise we raise ValueError.
      - If no index has both N[i] and S[i] individually viable, raise.
    """
    seat_profiles = getattr(profile, "seat_profiles", None)
    if not isinstance(seat_profiles, Mapping):
        return

    north = seat_profiles.get("N")
    south = seat_profiles.get("S")
    if north is None or south is None:
        return

    # NS coupling is enabled for all ns_role_mode values EXCEPT
    # "no_driver_no_index", which explicitly opts out of index coupling.
    _ns_mode = (
        getattr(profile, "ns_role_mode", "no_driver_no_index")
        or "no_driver_no_index"
    )
    ns_coupling_enabled = _ns_mode != "no_driver_no_index"
    if not ns_coupling_enabled:
        return

    n_subs = getattr(north, "subprofiles", None)
    s_subs = getattr(south, "subprofiles", None)
    if not isinstance(n_subs, Sequence) or not isinstance(s_subs, Sequence):
        return
    if len(n_subs) <= 1 or len(s_subs) <= 1 or len(n_subs) != len(s_subs):
        # No NS coupling scenario we care about.
        return

    individually_viable_indices: list[int] = []

    for idx, (n_sub, s_sub) in enumerate(zip(n_subs, s_subs)):
        # Use the light viability check (doesn't require dealing cards)
        n_ok = _subprofile_is_viable_light(n_sub)
        s_ok = _subprofile_is_viable_light(s_sub)

        # If either side is individually impossible, we skip this index.
        # The light validator already enforces "at least one viable subprofile
        # per seat" globally.
        if not (n_ok and s_ok):
            continue

        individually_viable_indices.append(idx)

        # For indices where both sides are individually viable, the pair must
        # also be jointly viable (cannot over-demand any suit).
        if not _ns_pair_jointly_viable(n_sub, s_sub):
            raise ValueError(
                "NS index-coupled subprofile pair is not jointly viable "
                f"at index {idx}"
            )

    # If NS coupling is present but there is *no* index where both N and S are
    # individually viable, the profile is unusable.
    if not individually_viable_indices:
        raise ValueError("No NS index-coupled subprofile pair is jointly viable")