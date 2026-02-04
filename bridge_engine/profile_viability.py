"""
Extended profile-level viability helpers.

Historically these lived in a `profile_viability` module. The current
per-seat implementation lives in `seat_viability`. This module:

  * re-exports `_subprofile_is_viable` for backwards compatibility, and
  * provides a profile-level `validate_profile_viability(...)` that adds
    NS index-coupling checks on top of the lighter per-seat validation.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from .seat_viability import (
    _subprofile_is_viable,
    _subprofile_is_viable_light,
    validate_profile_viability_light,
)

__all__ = ["_subprofile_is_viable", "validate_profile_viability"]


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


def validate_profile_viability(profile: Any) -> None:
    """
    Extended profile viability:

      1. Run validate_profile_viability_light(...) to enforce per-seat and
         per-subprofile invariants.
      2. If NS index-coupling is enabled and both N/S have >1 subprofiles
         with equal lengths, then for each index i:

            - If both N[i] and S[i] are individually viable, they must also
              be jointly viable as a pair; otherwise we raise ValueError.

         Additionally, if there is no index where BOTH N[i] and S[i] are
         individually viable, we also raise ValueError.
    """
    # Step 1: baseline light validation (per-seat checks, HCP, shape, etc.).
    validate_profile_viability_light(profile)

    # Step 2: NS index-coupling overlay.
    seat_profiles = getattr(profile, "seat_profiles", None)
    if not isinstance(seat_profiles, Mapping):
        return

    north = seat_profiles.get("N")
    south = seat_profiles.get("S")
    if north is None or south is None:
        return

    # Respect the same flag semantics as the deal generator.
    ns_coupling_enabled = bool(getattr(profile, "ns_index_coupling_enabled", True))
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