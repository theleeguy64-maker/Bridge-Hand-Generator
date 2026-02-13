# bridge_engine/deal_generator_v2.py
#
# v2 shape-help helpers extracted from deal_generator.py (Batch 3, #7).
# These functions implement the "shape help" system: dispersion checking,
# pre-allocation, constrained fill, RS suit pre-selection, and the
# _deal_with_help orchestrator.
#
# None of these functions use isinstance(x, SeatProfile) or reference
# _match_seat, so they have no monkeypatch sensitivity.
# ---------------------------------------------------------------------------
from __future__ import annotations

import sys
from typing import Callable, Dict, List, Optional, Set, Tuple

import math
import random

from .deal_generator_types import (
    Seat, Card, SeatFailCounts, SeatSeenCounts,
    Deal, DealGenerationError,
    SHAPE_PROB_GTE, SHAPE_PROB_THRESHOLD,
    PRE_ALLOCATE_FRACTION,
    RS_PRE_ALLOCATE_FRACTION, RS_PRE_ALLOCATE_HCP_RETRIES,
    MAX_BOARD_ATTEMPTS, SUBPROFILE_REROLL_INTERVAL, RS_REROLL_INTERVAL,
    FULL_DECK_HCP_SUM, FULL_DECK_HCP_SUM_SQ, MAX_HAND_HCP,
    _CARD_HCP,
)
# _DEBUG_ON_MAX_ATTEMPTS and _DEBUG_ON_ATTEMPT_FAILURE_ATTRIBUTION are
# mutable module-level hooks that tests set on the facade module (dg).
# Read them through the late-imported _dg reference at call time.
# ENABLE_HCP_FEASIBILITY_CHECK and HCP_FEASIBILITY_NUM_SD are read at call
# time from the deal_generator facade module (late import) so that tests
# which monkeypatch `dg.ENABLE_HCP_FEASIBILITY_CHECK` still work.  The
# facade re-exports these from deal_generator_types via `from ... import *`.
from .deal_generator_helpers import (
    _check_hcp_feasibility, _build_deck, _compute_viability_summary,
    _vulnerability_for_board,
)
from .hand_profile import HandProfile, SeatProfile, SubProfile, SuitRange
from .seat_viability import _match_seat


# ---------------------------------------------------------------------------
# v2 shape-help helpers
# ---------------------------------------------------------------------------


def _resolve_rs_ranges(
    rs: object,
    pre_selected_suits: List[str],
) -> Dict[str, object]:
    """
    Resolve the effective RS suit ranges for pre-selected suits.

    Handles pair_overrides: when required_suits_count == 2 and a matching
    pair override exists, uses the override's first_range/second_range
    instead of the default suit_ranges.

    Args:
        rs: The random_suit_constraint object (must have required_suits_count,
            pair_overrides, suit_ranges attributes).
        pre_selected_suits: List of suit letters chosen for this seat.

    Returns:
        Dict mapping suit letter → SuitRange object.
    """
    ranges: Dict[str, SuitRange] = {}

    if (
        rs.required_suits_count == 2
        and rs.pair_overrides
        and len(pre_selected_suits) == 2
    ):
        sorted_pair = tuple(sorted(pre_selected_suits))
        matched = None
        for po in rs.pair_overrides:
            if tuple(sorted(po.suits)) == sorted_pair:
                matched = po
                break
        if matched is not None:
            ranges[matched.suits[0]] = matched.first_range
            ranges[matched.suits[1]] = matched.second_range
        else:
            for idx, suit in enumerate(pre_selected_suits):
                if idx < len(rs.suit_ranges):
                    ranges[suit] = rs.suit_ranges[idx]
    else:
        for idx, suit in enumerate(pre_selected_suits):
            if idx < len(rs.suit_ranges):
                ranges[suit] = rs.suit_ranges[idx]

    return ranges


def _dispersion_check(
    chosen_subprofiles: Dict[Seat, "SubProfile"],
    threshold: float = SHAPE_PROB_THRESHOLD,
    rs_pre_selections: Optional[Dict[Seat, List[str]]] = None,
) -> Set[str]:
    """
    Identify seats with tight shape constraints that need pre-allocation help.

    For each seat, examines every suit's min_cards in the standard constraints.
    If any suit has P(>= min_cards) <= threshold, the seat is "tight".

    When rs_pre_selections is provided, also checks the RS (Random Suit)
    constraint for pre-selected suits.  This allows RS seats whose shape
    requirement lives entirely in the RS constraint (not in standard
    min_cards) to be flagged as tight — e.g. a weak-2 opener needing
    exactly 6 cards in one suit.

    Args:
        chosen_subprofiles: The selected subprofile for each seat.
        threshold: Probability cutoff (default 0.19 = 19%).
        rs_pre_selections: Optional dict mapping seat -> pre-selected RS
            suit letters (from _pre_select_rs_suits).  When None, only
            standard constraints are checked (backward compatible).

    Returns:
        Set of seat names (e.g. {"N", "S"}) that need shape help.
        Empty set if no seats are tight.
    """
    tight_seats: set = set()

    for seat, sub in chosen_subprofiles.items():
        std = getattr(sub, "standard", None)
        if std is None:
            continue

        # Check each suit for tight shape constraints (standard).
        for suit_attr in ("spades", "hearts", "diamonds", "clubs"):
            suit_range = getattr(std, suit_attr, None)
            if suit_range is None:
                continue
            min_cards = getattr(suit_range, "min_cards", 0)
            if min_cards <= 0:
                continue
            prob = SHAPE_PROB_GTE.get(min_cards, 0.0)
            if prob <= threshold:
                tight_seats.add(seat)
                break  # One tight suit is enough to flag the seat

    # --- RS-aware tightness check ---
    # For seats with pre-selected RS suits, check whether the RS
    # suit_ranges have min_cards tight enough to flag the seat.
    if rs_pre_selections:
        for seat, pre_suits in rs_pre_selections.items():
            if seat in tight_seats:
                continue  # Already flagged by standard constraints
            sub = chosen_subprofiles.get(seat)
            if sub is None:
                continue
            rs = getattr(sub, "random_suit_constraint", None)
            if rs is None:
                continue

            ranges_by_suit = _resolve_rs_ranges(rs, pre_suits)

            # Check each RS suit's min_cards against the probability table.
            for suit_letter, sr in ranges_by_suit.items():
                min_cards = getattr(sr, "min_cards", 0)
                if min_cards <= 0:
                    continue
                prob = SHAPE_PROB_GTE.get(min_cards, 0.0)
                if prob <= threshold:
                    tight_seats.add(seat)
                    break  # One tight RS suit is enough

    return tight_seats


def _pre_select_rs_suits(
    rng: random.Random,
    chosen_subprofiles: Dict[Seat, "SubProfile"],
) -> Dict[Seat, List[str]]:
    """
    Pre-select Random Suit choices for all RS seats BEFORE dealing.

    For each seat whose chosen subprofile has a random_suit_constraint,
    randomly choose required_suits_count suits from allowed_suits.
    This is the same selection logic as _match_random_suit_with_attempt()
    (seat_viability.py:140), but performed up front so we can:
      - flag RS seats as "tight" in _dispersion_check()
      - pre-allocate cards for the chosen RS suit(s)
      - use the pre-committed suits during matching (no random re-pick)

    Args:
        rng: Random number generator.
        chosen_subprofiles: The selected subprofile for each seat.

    Returns:
        Dict mapping seat -> list of chosen suit letters (e.g. {"W": ["H"]}).
        Empty dict if no seats have RS constraints.
    """
    rs_pre: Dict[Seat, List[str]] = {}

    for seat, sub in chosen_subprofiles.items():
        rs = getattr(sub, "random_suit_constraint", None)
        if rs is None:
            continue
        allowed = list(rs.allowed_suits)
        if not allowed or rs.required_suits_count <= 0:
            continue
        if rs.required_suits_count > len(allowed):
            continue
        chosen_suits = rng.sample(allowed, rs.required_suits_count)
        rs_pre[seat] = chosen_suits

    return rs_pre


def _random_deal(
    rng: random.Random,
    deck: List[Card],
    n: int,
) -> List[Card]:
    """
    Deal n random cards from deck, removing them from deck (mutating).

    If deck has fewer than n cards, deals whatever remains.
    If n <= 0, returns empty list.

    Args:
        rng: Random number generator.
        deck: Mutable list of cards to draw from. Modified in place.
        n: Number of cards to deal.

    Returns:
        List of dealt cards (may be fewer than n if deck was smaller).
    """
    if n <= 0:
        return []
    take = min(n, len(deck))
    if take <= 0:
        return []

    # The deck is already shuffled, so the first `take` cards are a random
    # sample.  Slicing is much faster than rng.sample + set-filter:
    # O(take) slice + O(remaining) shift vs O(take) sample + O(deck) filter.
    hand = deck[:take]
    del deck[:take]
    return hand


def _get_suit_maxima(
    subprofile: "SubProfile",
    rs_pre_selected: Optional[List[str]] = None,
) -> Dict[str, int]:
    """
    Extract the effective max_cards per suit from a subprofile.

    Combines standard constraint maxima with RS constraint maxima for
    pre-selected suits.  Returns a dict mapping suit letter → max cards.

    E.g. standard has max_cards=13 for all suits, but RS says max=6 for
    spades → effective max for S is 6.
    """
    maxima: Dict[str, int] = {"S": 13, "H": 13, "D": 13, "C": 13}

    # Standard constraints.
    std = getattr(subprofile, "standard", None)
    if std is not None:
        for suit_letter, suit_attr in [
            ("S", "spades"), ("H", "hearts"),
            ("D", "diamonds"), ("C", "clubs"),
        ]:
            sr = getattr(std, suit_attr, None)
            if sr is not None:
                mc = getattr(sr, "max_cards", 13)
                if mc < maxima[suit_letter]:
                    maxima[suit_letter] = mc

    # RS constraints: enforce max_cards for pre-selected suits.
    rs = getattr(subprofile, "random_suit_constraint", None)
    if rs is not None and rs_pre_selected:
        ranges_by_suit = _resolve_rs_ranges(rs, rs_pre_selected)

        for suit_letter, sr in ranges_by_suit.items():
            mc = getattr(sr, "max_cards", 13)
            if mc < maxima[suit_letter]:
                maxima[suit_letter] = mc

    return maxima


def _constrained_fill(
    deck: List[Card],
    n: int,
    pre_cards: List[Card],
    suit_maxima: Dict[str, int],
    total_max_hcp: int = 40,
    rs_suit_hcp_max: Optional[Dict[str, int]] = None,
) -> List[Card]:
    """
    Fill n cards from a shuffled deck, skipping cards that would bust
    a suit maximum, push total HCP over the maximum, or exceed a
    per-suit HCP cap for RS suits.  Skipped cards remain in the deck
    for other seats.

    Since the deck is already shuffled, walking front-to-back and
    accepting/skipping is equivalent to random selection with rejection.

    Args:
        deck: Shuffled deck (mutable, modified in place).
        n: Number of cards to fill.
        pre_cards: Cards already in hand (pre-allocated), used to count
            current suit holdings and HCP.
        suit_maxima: Max cards per suit {S: max, H: max, D: max, C: max}.
        total_max_hcp: Maximum total HCP for the hand (default 40 = no limit).
        rs_suit_hcp_max: Optional per-suit HCP cap for RS suits, e.g.
            {"H": 7} means hearts can't exceed 7 HCP.  Only honor cards
            are checked — spot cards (0 HCP) are always accepted.
            Default None = no per-suit HCP enforcement.

    Returns:
        List of accepted cards (may be fewer than n if deck exhausted).
    """
    if n <= 0:
        return []

    # Count suits and HCP already held from pre-allocation.
    suit_count: Dict[str, int] = {"S": 0, "H": 0, "D": 0, "C": 0}
    current_hcp = 0
    for c in pre_cards:
        suit_count[c[1]] += 1
        current_hcp += _CARD_HCP[c]

    # Track per-suit HCP for RS suits that have a cap.
    # Only initialized when rs_suit_hcp_max is provided (zero overhead otherwise).
    suit_hcp: Dict[str, int] = {}
    if rs_suit_hcp_max:
        for c in pre_cards:
            s = c[1]
            if s in rs_suit_hcp_max:
                suit_hcp[s] = suit_hcp.get(s, 0) + _CARD_HCP[c]

    accepted: List[Card] = []
    remaining: List[Card] = []

    for card in deck:
        if len(accepted) >= n:
            # Already have enough — push rest to remaining untouched.
            remaining.append(card)
            continue

        card_hcp = _CARD_HCP[card]
        suit = card[1]

        # Skip if this card would bust the suit maximum.
        if suit_count[suit] >= suit_maxima.get(suit, 13):
            remaining.append(card)
            continue

        # Skip if this honor card would push total HCP over the maximum.
        # Only skip cards with HCP > 0 — spot cards are always accepted
        # since they don't change the HCP situation.
        if card_hcp > 0 and current_hcp + card_hcp > total_max_hcp:
            remaining.append(card)
            continue

        # Skip if this honor card would bust the per-suit HCP cap (#13).
        # Only applies to RS suits with an explicit max_hcp.
        if rs_suit_hcp_max and suit in rs_suit_hcp_max:
            if card_hcp > 0 and suit_hcp.get(suit, 0) + card_hcp > rs_suit_hcp_max[suit]:
                remaining.append(card)
                continue

        accepted.append(card)
        suit_count[suit] += 1
        current_hcp += card_hcp
        # Update per-suit HCP tracking for RS suits.
        if rs_suit_hcp_max and suit in rs_suit_hcp_max:
            suit_hcp[suit] = suit_hcp.get(suit, 0) + card_hcp

    deck[:] = remaining
    return accepted


# ---------------------------------------------------------------------------
# HCP feasibility utilities
#
# These functions support early rejection of hands whose pre-allocated cards
# make the target HCP range statistically implausible.  The check runs after
# shape pre-allocation but before the random fill, saving the cost of dealing.
# HCP utilities (_card_hcp, _deck_hcp_stats, _check_hcp_feasibility) are
# imported from deal_generator_helpers (re-exported via *).

def _pre_allocate(
    rng: random.Random,
    deck: List[Card],
    subprofile: "SubProfile",
    fraction: float = PRE_ALLOCATE_FRACTION,
) -> List[Card]:
    """
    Pre-allocate a fraction of suit minima for a tight seat.

    For each suit in the subprofile's standard constraints, if min_cards > 0,
    allocate floor(min_cards * fraction) cards of that suit from the deck.

    This helps tight seats get a head start on their required suits without
    over-constraining the deck for other seats.

    Args:
        rng: Random number generator.
        deck: Mutable list of cards. Modified in place (cards removed).
        subprofile: The chosen subprofile for this seat.
        fraction: Fraction of minima to pre-allocate (default 0.75).

    Returns:
        List of pre-allocated cards (may be empty).
    """
    std = getattr(subprofile, "standard", None)
    if std is None:
        return []

    # Build suit index once — avoids N full-deck scans (one per suit).
    # Pre-initialized dict avoids setdefault overhead on every card.
    suit_cards: Dict[str, List[Card]] = {"S": [], "H": [], "D": [], "C": []}
    for c in deck:
        suit_cards[c[1]].append(c)

    pre_allocated: List[Card] = []

    # Process each suit's minimum.  Card format is rank+suit, e.g. "AS".
    # Suit letter is at index 1 (S/H/D/C).
    for suit_letter, suit_attr in [
        ("S", "spades"), ("H", "hearts"),
        ("D", "diamonds"), ("C", "clubs"),
    ]:
        suit_range = getattr(std, suit_attr, None)
        if suit_range is None:
            continue
        min_cards = getattr(suit_range, "min_cards", 0)
        if min_cards <= 0:
            continue

        to_allocate = math.floor(min_cards * fraction)
        if to_allocate <= 0:
            continue

        available = suit_cards.get(suit_letter, [])
        if not available:
            continue

        # Don't try to allocate more than available.
        actual = min(to_allocate, len(available))
        chosen = rng.sample(available, actual)
        pre_allocated.extend(chosen)

    # Remove all chosen cards from deck in one pass (instead of per-suit).
    if pre_allocated:
        chosen_set = set(pre_allocated)
        deck[:] = [c for c in deck if c not in chosen_set]

    return pre_allocated


def _pre_allocate_rs(
    rng: random.Random,
    deck: List[Card],
    subprofile: "SubProfile",
    pre_selected_suits: List[str],
    fraction: float = RS_PRE_ALLOCATE_FRACTION,
) -> List[Card]:
    """
    Pre-allocate cards for RS (Random Suit) pre-selected suits.

    Uses RS_PRE_ALLOCATE_FRACTION (default 1.0) so RS suits are fully
    populated at pre-allocation time with HCP targeting.  This avoids
    the random fill blindly adding cards that bust the RS suit's HCP
    window.  Standard pre-allocation still uses PRE_ALLOCATE_FRACTION.

    Handles pair_overrides: when required_suits_count == 2 and a matching
    pair override exists, uses the override ranges instead of the default
    suit_ranges.

    Args:
        rng: Random number generator.
        deck: Mutable list of cards. Modified in place (cards removed).
        subprofile: The chosen subprofile (must have random_suit_constraint).
        pre_selected_suits: List of suit letters pre-selected for RS.
        fraction: Fraction of RS minima to pre-allocate (default 1.0).

    Returns:
        List of pre-allocated cards (may be empty).
    """
    rs = getattr(subprofile, "random_suit_constraint", None)
    if rs is None:
        return []

    ranges_by_suit = _resolve_rs_ranges(rs, pre_selected_suits)

    # Build suit index once — suits are disjoint so processing order
    # doesn't affect available pools across different suits.
    # Pre-initialized dict avoids setdefault overhead on every card.
    suit_cards: Dict[str, List[Card]] = {"S": [], "H": [], "D": [], "C": []}
    for c in deck:
        suit_cards[c[1]].append(c)

    pre_allocated: List[Card] = []

    for suit_letter, sr in ranges_by_suit.items():
        min_cards = getattr(sr, "min_cards", 0)
        if min_cards <= 0:
            continue

        to_allocate = math.floor(min_cards * fraction)
        if to_allocate <= 0:
            continue

        available = suit_cards.get(suit_letter, [])
        if not available:
            continue

        # Don't try to allocate more than available.
        actual = min(to_allocate, len(available))

        # HCP-targeted rejection sampling: try multiple samples and pick
        # the first whose pro-rated HCP is on-track for the suit's target.
        # This dramatically improves success rates for tight HCP constraints
        # (e.g. W in "Defense to Weak 2s" needs 5-7 HCP in exactly 6 cards).
        min_hcp = getattr(sr, "min_hcp", None)
        max_hcp = getattr(sr, "max_hcp", None)
        use_hcp_targeting = (
            RS_PRE_ALLOCATE_HCP_RETRIES > 0
            and min_hcp is not None
            and max_hcp is not None
            and min_cards > 0
        )

        if use_hcp_targeting:
            # Pro-rate HCP target to the pre-allocated card count.
            # E.g. 6 cards need 5-7 HCP → 3 pre-allocated need 2-4 HCP.
            target_low = math.floor(min_hcp * actual / min_cards)
            target_high = math.ceil(max_hcp * actual / min_cards)

            chosen = rng.sample(available, actual)
            for _retry in range(RS_PRE_ALLOCATE_HCP_RETRIES):
                sample_hcp = sum(_CARD_HCP[c] for c in chosen)
                if target_low <= sample_hcp <= target_high:
                    break  # Good HCP — use this sample.
                # Bad HCP — resample.
                chosen = rng.sample(available, actual)
            # After retries, use whatever we ended up with (last sample).
        else:
            chosen = rng.sample(available, actual)

        pre_allocated.extend(chosen)

    # Remove all chosen cards from deck in one pass (instead of per-suit).
    if pre_allocated:
        chosen_set = set(pre_allocated)
        deck[:] = [c for c in deck if c not in chosen_set]

    return pre_allocated


def _deal_with_help(
    rng: random.Random,
    deck: List[Card],
    chosen_subprofiles: Dict[Seat, "SubProfile"],
    tight_seats: set,
    dealing_order: List[Seat],
    rs_pre_selections: Optional[Dict[Seat, List[str]]] = None,
) -> Tuple[Optional[Dict[Seat, List[Card]]], Optional[Seat]]:
    """
    Deal 52 cards to 4 seats, giving shape help to tight seats.

    For each seat in dealing_order:
      - If tight: pre-allocate fraction of suit minima, fill to 13 randomly
      - If not tight (and not last): deal 13 random cards
      - Last seat: gets whatever remains (always 13 if deck started at 52)

    When ENABLE_HCP_FEASIBILITY_CHECK is True, an early rejection check runs
    after pre-allocation for each tight seat.  If the pre-allocated cards make
    the seat's total HCP target statistically implausible, the function returns
    (None, rejected_seat) immediately — saving the cost of dealing the
    remaining cards and running the full matching pipeline.

    Mutates deck (empties it, or partially empties on early rejection).

    Args:
        rng: Random number generator.
        deck: 52-card deck (mutable, will be emptied).
        chosen_subprofiles: Selected subprofile per seat.
        tight_seats: Set of seats needing shape help.
        dealing_order: Order to deal seats.
        rs_pre_selections: Optional dict mapping seat -> pre-selected RS
            suit letters.  When provided, tight RS seats also get cards
            pre-allocated for their RS suit(s) via _pre_allocate_rs().

    Returns:
        (hands, None)           — on success: hands maps each seat to 13 cards.
        (None, rejected_seat)   — on early HCP rejection: the seat that failed.
    """
    # Late import: read gate flags from the facade module so that tests
    # which monkeypatch dg.ENABLE_HCP_FEASIBILITY_CHECK still work.
    from . import deal_generator as _dg
    _enable_hcp = _dg.ENABLE_HCP_FEASIBILITY_CHECK
    _hcp_num_sd = _dg.HCP_FEASIBILITY_NUM_SD

    hands: Dict[Seat, List[Card]] = {}

    # Phase 1: Pre-allocate for ALL tight seats (including last seat).
    # This ensures every tight seat gets some guaranteed cards from its
    # required suits, regardless of dealing order position.
    pre_allocated: Dict[Seat, List[Card]] = {}
    for seat in dealing_order:
        if seat not in tight_seats:
            continue
        sub = chosen_subprofiles.get(seat)
        if sub is None:
            continue
        # Standard pre-allocation.
        pre = _pre_allocate(rng, deck, sub)
        # RS pre-allocation: if this seat has pre-selected RS suits.
        if rs_pre_selections and seat in rs_pre_selections:
            rs_pre = _pre_allocate_rs(
                rng, deck, sub, rs_pre_selections[seat]
            )
            pre = pre + rs_pre
        if pre:
            pre_allocated[seat] = pre

    # Phase 2: HCP feasibility check on all pre-allocated seats.
    # Run AFTER all pre-allocations so the deck state reflects all
    # reservations (more accurate feasibility statistics).
    #
    # Incremental HCP tracking: full deck always has hcp_sum=40,
    # hcp_sum_sq=120.  Subtract pre-allocated cards' contributions
    # to avoid scanning the remaining deck.
    if _enable_hcp and pre_allocated:
        # Compute deck HCP stats from known full-deck constants
        # minus what was removed by pre-allocation.
        removed_hcp_sum = 0
        removed_hcp_sum_sq = 0
        for cards in pre_allocated.values():
            for c in cards:
                v = _CARD_HCP[c]
                removed_hcp_sum += v
                removed_hcp_sum_sq += v * v
        deck_hcp_sum = FULL_DECK_HCP_SUM - removed_hcp_sum
        deck_hcp_sum_sq = FULL_DECK_HCP_SUM_SQ - removed_hcp_sum_sq
        deck_size = len(deck)

        for seat in dealing_order:
            pre = pre_allocated.get(seat)
            if not pre:
                continue
            sub = chosen_subprofiles.get(seat)
            if sub is None:
                continue
            std = getattr(sub, "standard", None)
            if std is None:
                continue
            drawn_hcp = sum(_CARD_HCP[c] for c in pre)
            cards_remaining = 13 - len(pre)
            if cards_remaining > 0 and deck_size > 0:
                if not _check_hcp_feasibility(
                    drawn_hcp,
                    cards_remaining,
                    deck_size,
                    deck_hcp_sum,
                    deck_hcp_sum_sq,
                    std.total_min_hcp,
                    std.total_max_hcp,
                    _hcp_num_sd,
                ):
                    return None, seat  # Early HCP rejection

    # Phase 3: Fill each seat to 13 cards.
    # For non-last seats, use constrained fill to skip cards that would
    # bust a suit maximum.  Skipped cards stay in the deck for later seats.
    for i, seat in enumerate(dealing_order):
        is_last = (i == len(dealing_order) - 1)
        pre = pre_allocated.get(seat, [])

        if is_last:
            # Last seat: pre-allocated cards + whatever remains in the deck.
            hands[seat] = pre + list(deck)
            deck.clear()
        else:
            remaining_needed = 13 - len(pre)
            sub = chosen_subprofiles.get(seat)
            if sub is not None:
                # Constrained fill: skip cards that would bust suit max,
                # push total HCP over the maximum, or exceed per-suit
                # HCP cap for RS suits (#13).
                rs_for_seat = (
                    rs_pre_selections.get(seat)
                    if rs_pre_selections else None
                )
                maxima = _get_suit_maxima(sub, rs_for_seat)
                std = getattr(sub, "standard", None)
                max_hcp = (
                    getattr(std, "total_max_hcp", MAX_HAND_HCP)
                    if std is not None else MAX_HAND_HCP
                )

                # Extract per-suit HCP max from RS constraints (#13).
                # Only needed when RS suits have an explicit max_hcp cap.
                rs_hcp_max = None
                if rs_for_seat:
                    rs = getattr(sub, "random_suit_constraint", None)
                    if rs is not None:
                        resolved = _resolve_rs_ranges(rs, rs_for_seat)
                        rs_hcp_max = {}
                        for s_letter, sr in resolved.items():
                            mhcp = getattr(sr, "max_hcp", None)
                            if mhcp is not None and mhcp < MAX_HAND_HCP:
                                rs_hcp_max[s_letter] = mhcp
                        if not rs_hcp_max:
                            rs_hcp_max = None

                fill = _constrained_fill(
                    deck, remaining_needed, pre, maxima, max_hcp,
                    rs_hcp_max,
                )
            else:
                fill = _random_deal(rng, deck, remaining_needed)
            hands[seat] = pre + fill

    return hands, None


# ---------------------------------------------------------------------------
# Auto-compute dealing order: least constrained seat last.
#
# v2's only meaningful use of dealing order is "last seat gets remainder
# without constrained fill."  We compute the optimal order from the chosen
# subprofiles so that the least constrained seat is always last.
# ---------------------------------------------------------------------------

# Risk scores for subprofile constraint types (higher = more constrained).
_CONSTRAINT_RISK: Dict[str, float] = {
    "rs": 1.0,         # Random Suit — must go first; others depend on it
    "pc": 0.5,         # Partner Contingent
    "oc": 0.5,         # Opponent Contingent
    "standard": 0.0,   # No cross-seat dependency
}

_CLOCKWISE = ["N", "E", "S", "W"]


def _subprofile_constraint_type(sub: "SubProfile") -> str:
    """Classify a subprofile as 'rs', 'pc', 'oc', or 'standard'."""
    if getattr(sub, "random_suit_constraint", None) is not None:
        return "rs"
    if getattr(sub, "partner_contingent_constraint", None) is not None:
        return "pc"
    if getattr(sub, "opponents_contingent_suit_constraint", None) is not None:
        return "oc"
    return "standard"


def _compute_dealing_order(
    chosen_subprofiles: Dict[Seat, "SubProfile"],
    dealer: Seat,
) -> List[Seat]:
    """
    Compute optimal dealing order with the least constrained seat last.

    Seats are sorted by constraint risk (descending).  The highest-risk
    seats go first (best card selection from fuller deck), and the
    lowest-risk seat goes last (gets remainder without constrained fill).

    Tiebreakers:
      1. Narrower total HCP range = higher effective risk (dealt earlier).
      2. Clockwise position from dealer (earlier = dealt earlier).

    Args:
        chosen_subprofiles: The subprofile selected for each seat this board.
        dealer: The dealer seat (used for clockwise tiebreaker).

    Returns:
        List of 4 seats in dealing order.
    """
    # Build clockwise order starting from dealer for tiebreaking.
    d_idx = _CLOCKWISE.index(dealer)
    clockwise_from_dealer = _CLOCKWISE[d_idx:] + _CLOCKWISE[:d_idx]

    def _sort_key(seat: Seat):
        sub = chosen_subprofiles.get(seat)
        if sub is None:
            # No subprofile → unconstrained → lowest risk, ideal for last.
            return (0.0, 0, 0)

        ctype = _subprofile_constraint_type(sub)
        risk = _CONSTRAINT_RISK[ctype]

        # HCP tiebreaker: narrower range = harder = higher effective risk.
        std = getattr(sub, "standard", None)
        if std is not None:
            hcp_min = getattr(std, "total_min_hcp", 0)
            hcp_max = getattr(std, "total_max_hcp", 37)
            hcp_range = max(hcp_max - hcp_min, 0)
        else:
            hcp_range = 37  # unconstrained

        # Clockwise tiebreaker: earlier clockwise = dealt earlier.
        cw_pos = clockwise_from_dealer.index(seat)

        # Sort descending by risk, ascending by hcp_range (narrow=first),
        # ascending by clockwise position.
        # Negate risk so default ascending sort puts high risk first.
        return (-risk, hcp_range, cw_pos)

    return sorted(clockwise_from_dealer, key=_sort_key)


def _build_processing_order(
    profile: "HandProfile",
    dealing_order: List[Seat],
    chosen_subprofiles: Dict[Seat, "SubProfile"],
) -> List[Seat]:
    """
    Build seat processing order: RS seats first, then everything else.

    RS seats must be processed before PC/OC seats so that partner/opponent
    RS choices are visible during matching.

    Args:
        profile: The HandProfile with seat constraints.
        dealing_order: Base dealing order.
        chosen_subprofiles: Selected subprofile per seat.

    Returns:
        List of constrained seats, RS first, preserving dealing_order within
        each group.
    """
    rs_seats: List[Seat] = []
    other_seats: List[Seat] = []
    for seat in dealing_order:
        sp = profile.seat_profiles.get(seat)
        if not isinstance(sp, SeatProfile) or not sp.subprofiles:
            continue
        sub = chosen_subprofiles.get(seat)
        if sub and getattr(sub, "random_suit_constraint", None) is not None:
            rs_seats.append(seat)
        else:
            other_seats.append(seat)
    return rs_seats + other_seats


# ---------------------------------------------------------------------------
# v2 constrained deal builder (Batch 4A, #7)
# ---------------------------------------------------------------------------


def _build_single_constrained_deal_v2(
    rng: random.Random,
    profile: "HandProfile",
    board_number: int,
    debug_board_stats: Optional[
        Callable[["SeatFailCounts", "SeatSeenCounts"], None]
    ] = None,
) -> "Deal":
    """
    Build a single constrained deal using shape-based help (v2 algorithm).

    Key differences from v1 (_build_single_constrained_deal):
      - Uses _dispersion_check() to identify tight seats BEFORE dealing
      - Pre-allocates 75% of suit minima for tight seats via _deal_with_help()
      - No hardest-seat selection or v1 constructive gates
      - Full failure attribution (seat_fail_as_seat, global_other,
        global_unchecked, hcp, shape) + debug hooks

    Old v1 function remains untouched.  This is a parallel implementation.

    Args:
        rng: Random number generator (seeded for reproducibility).
        profile: The HandProfile with seat constraints.
        board_number: 1-based board number.
        debug_board_stats: Optional callback receiving (seat_fail_counts,
            seat_seen_counts) on success or exhaustion.

    Returns:
        A Deal instance with matched hands.

    Raises:
        DealGenerationError: If no valid deal found after MAX_BOARD_ATTEMPTS.
    """
    # Late import: _select_subprofiles_for_board lives in the facade module
    # (deal_generator.py) because it uses isinstance(x, SeatProfile) checks
    # that tests monkeypatch through the facade namespace.
    from . import deal_generator as _dg

    # Profile's stored dealing order — used only for coupling driver
    # selection in _select_subprofiles_for_board().  The actual dealing
    # order is auto-computed below from the chosen subprofiles.
    profile_dealing_order: List[Seat] = list(profile.hand_dealing_order)

    # ------------------------------------------------------------------
    # FAST PATH: invariants-safety profiles (same as v1)
    # ------------------------------------------------------------------
    if getattr(profile, "is_invariants_safety_profile", False):
        deck = _build_deck()
        rng.shuffle(deck)
        hands: Dict[Seat, List[Card]] = {}
        idx = 0
        for seat in profile_dealing_order:
            hands[seat] = deck[idx : idx + 13]
            idx += 13
        return Deal(
            board_number=board_number,
            dealer=profile.dealer,
            vulnerability=_vulnerability_for_board(board_number),
            hands=hands,
        )

    # ------------------------------------------------------------------
    # Full constrained path
    # ------------------------------------------------------------------

    # Select subprofiles once per board (index-coupled where applicable).
    chosen_subprofiles, chosen_indices = _dg._select_subprofiles_for_board(
        rng, profile, profile_dealing_order
    )

    # Auto-compute dealing order from chosen subprofiles:
    # least constrained seat last (gets remainder without constrained fill).
    dealing_order = _compute_dealing_order(chosen_subprofiles, profile.dealer)

    # Pre-select RS suits BEFORE dealing so we can:
    #   (a) flag RS seats as tight in the dispersion check,
    #   (b) pre-allocate cards for the RS suit(s),
    #   (c) use the pre-committed suits during matching.
    rs_pre_selections = _pre_select_rs_suits(rng, chosen_subprofiles)

    # Identify tight seats that need shape help (RS-aware).
    tight_seats = _dispersion_check(
        chosen_subprofiles, rs_pre_selections=rs_pre_selections
    )

    # Build processing order: RS seats first so PC/OC can see partner's
    # RS choices, then everything else.
    processing_order = _build_processing_order(
        profile, dealing_order, chosen_subprofiles
    )

    # ------------------------------------------------------------------
    # Per-board failure attribution counters (D7)
    # ------------------------------------------------------------------
    # seat_fail_as_seat: seat was the first to fail on an attempt
    seat_fail_as_seat: Dict[Seat, int] = {}
    # seat_fail_global_other: seat passed, but a later seat failed
    seat_fail_global_other: Dict[Seat, int] = {}
    # seat_fail_global_unchecked: seat was never checked (early break)
    seat_fail_global_unchecked: Dict[Seat, int] = {}
    # HCP vs shape breakdown of seat-level failures
    seat_fail_hcp: Dict[Seat, int] = {}
    seat_fail_shape: Dict[Seat, int] = {}
    # Simple per-seat fail/seen counters (for debug_board_stats callback)
    seat_fail_counts: Dict[Seat, int] = {}
    seat_seen_counts: Dict[Seat, int] = {}

    board_attempts = 0

    _max_attempts = _dg.MAX_BOARD_ATTEMPTS
    while board_attempts < _max_attempts:
        board_attempts += 1

        # Periodic subprofile re-roll: try different subprofile combinations.
        # This is critical for hard profiles with many subprofiles per seat
        # (e.g. N/E each have 4 → 16 combos, some much easier than others).
        # Re-selecting subprofiles also re-selects RS suits and rebuilds
        # processing order since different subprofiles may have different
        # constraint types (RS, OC, etc.).
        if (
            board_attempts > 1
            and SUBPROFILE_REROLL_INTERVAL > 0
            and (board_attempts - 1) % SUBPROFILE_REROLL_INTERVAL == 0
        ):
            chosen_subprofiles, chosen_indices = _dg._select_subprofiles_for_board(
                rng, profile, profile_dealing_order
            )
            # Recompute dealing order for new subprofile combination.
            dealing_order = _compute_dealing_order(
                chosen_subprofiles, profile.dealer
            )
            rs_pre_selections = _pre_select_rs_suits(rng, chosen_subprofiles)
            tight_seats = _dispersion_check(
                chosen_subprofiles, rs_pre_selections=rs_pre_selections
            )
            # Rebuild processing order since RS seats may have changed.
            processing_order = _build_processing_order(
                profile, dealing_order, chosen_subprofiles
            )

        # Periodic RS re-roll (more frequent): try different RS suit
        # combinations within the same subprofile selection.
        elif (
            board_attempts > 1
            and RS_REROLL_INTERVAL > 0
            and (board_attempts - 1) % RS_REROLL_INTERVAL == 0
        ):
            rs_pre_selections = _pre_select_rs_suits(rng, chosen_subprofiles)
            tight_seats = _dispersion_check(
                chosen_subprofiles, rs_pre_selections=rs_pre_selections
            )

        # Build and shuffle a full deck.
        deck = _build_deck()
        rng.shuffle(deck)

        # Deal with shape help for tight seats (RS-aware).
        hands, hcp_rejected_seat = _deal_with_help(
            rng, deck, chosen_subprofiles, tight_seats, dealing_order,
            rs_pre_selections=rs_pre_selections,
        )

        # ----- Early HCP rejection handling -----
        # If _deal_with_help detected that a tight seat's pre-allocated cards
        # make its HCP target statistically implausible, skip matching entirely.
        if hcp_rejected_seat is not None:
            # Attribute failure to the rejected seat (HCP-driven).
            seat_fail_as_seat[hcp_rejected_seat] = (
                seat_fail_as_seat.get(hcp_rejected_seat, 0) + 1
            )
            seat_fail_hcp[hcp_rejected_seat] = (
                seat_fail_hcp.get(hcp_rejected_seat, 0) + 1
            )
            seat_fail_counts[hcp_rejected_seat] = (
                seat_fail_counts.get(hcp_rejected_seat, 0) + 1
            )
            seat_seen_counts[hcp_rejected_seat] = (
                seat_seen_counts.get(hcp_rejected_seat, 0) + 1
            )
            # All other constrained seats: globally unchecked.
            for s in processing_order:
                if s == hcp_rejected_seat:
                    continue
                sp_check = profile.seat_profiles.get(s)
                if isinstance(sp_check, SeatProfile) and sp_check.subprofiles:
                    seat_fail_global_unchecked[s] = (
                        seat_fail_global_unchecked.get(s, 0) + 1
                    )
            # Fire per-attempt debug hook with current counters.
            if _dg._DEBUG_ON_ATTEMPT_FAILURE_ATTRIBUTION is not None:
                try:
                    _dg._DEBUG_ON_ATTEMPT_FAILURE_ATTRIBUTION(
                        profile,
                        board_number,
                        board_attempts,
                        dict(seat_fail_as_seat),
                        dict(seat_fail_global_other),
                        dict(seat_fail_global_unchecked),
                        dict(seat_fail_hcp),
                        dict(seat_fail_shape),
                    )
                except Exception as exc:
                    print(f"WARNING: debug hook failed: {exc}", file=sys.stderr)
            continue  # Skip matching, next attempt.
        # ----- end early HCP rejection handling -----

        # Match all seats against their constraints.
        all_matched = True
        # Pre-seed random_suit_choices with RS pre-selections so that:
        #   (a) RS matching uses the pre-committed suits instead of random,
        #   (b) PC/OC seats can see partner/opponent RS choices immediately.
        random_suit_choices: Dict[Seat, List[str]] = dict(rs_pre_selections)
        # Per-attempt tracking for global attribution.
        checked_seats_in_attempt: List[Seat] = []
        first_failed_seat: Optional[Seat] = None
        first_failed_stage_idx: Optional[int] = None

        for seat in processing_order:
            sp = profile.seat_profiles.get(seat)
            if not isinstance(sp, SeatProfile) or not sp.subprofiles:
                continue

            sub = chosen_subprofiles.get(seat)
            idx0 = chosen_indices.get(seat)

            if sub is None or idx0 is None:
                all_matched = False
                break

            # ---- Early total-HCP pre-check (perf optimisation) ----
            # Quick O(13) sum before the full _match_seat / _compute_suit_analysis
            # pipeline.  If the hand's total HCP is outside the subprofile's
            # standard range, we can reject immediately — avoids suit analysis,
            # RS matching, and all subprofile iteration overhead.
            # NOTE: Attribution is always "hcp" here even though the hand might
            # also fail shape checks.  This is a known diagnostic imprecision —
            # HCP is the *detected* cause since we check it first for speed.
            std_early = getattr(sub, "standard", None)
            if std_early is not None:
                hand_hcp_quick = sum(_CARD_HCP[c] for c in hands[seat])
                if (
                    hand_hcp_quick < std_early.total_min_hcp
                    or hand_hcp_quick > std_early.total_max_hcp
                ):
                    # Count as checked + failed (HCP).
                    checked_seats_in_attempt.append(seat)
                    seat_seen_counts[seat] = seat_seen_counts.get(seat, 0) + 1
                    all_matched = False
                    seat_fail_counts[seat] = seat_fail_counts.get(seat, 0) + 1
                    seat_fail_as_seat[seat] = seat_fail_as_seat.get(seat, 0) + 1
                    seat_fail_hcp[seat] = seat_fail_hcp.get(seat, 0) + 1
                    if first_failed_seat is None:
                        first_failed_seat = seat
                        first_failed_stage_idx = len(checked_seats_in_attempt) - 1
                    break
            # ---- end early total-HCP pre-check ----

            # Track that we checked this seat.
            checked_seats_in_attempt.append(seat)
            seat_seen_counts[seat] = seat_seen_counts.get(seat, 0) + 1

            matched, chosen_rs, fail_reason = _match_seat(
                profile=profile,
                seat=seat,
                hand=hands[seat],
                seat_profile=sp,
                chosen_subprofile=sub,
                chosen_subprofile_index_1based=idx0 + 1,
                random_suit_choices=random_suit_choices,
                rng=rng,
                rs_pre_selections=rs_pre_selections,
            )

            if matched and chosen_rs is not None:
                # Store RS choice so PC/OC seats can reference it.
                random_suit_choices[seat] = chosen_rs

            if not matched:
                all_matched = False
                seat_fail_counts[seat] = seat_fail_counts.get(seat, 0) + 1

                # This seat is the first failing seat on this attempt.
                seat_fail_as_seat[seat] = seat_fail_as_seat.get(seat, 0) + 1

                # Classify failure as HCP vs shape.
                if fail_reason == "hcp":
                    seat_fail_hcp[seat] = seat_fail_hcp.get(seat, 0) + 1
                elif fail_reason == "shape":
                    seat_fail_shape[seat] = seat_fail_shape.get(seat, 0) + 1
                # else: "other" or None — not classified

                # Record first-failure markers (only once per attempt).
                if first_failed_seat is None:
                    first_failed_seat = seat
                    first_failed_stage_idx = len(checked_seats_in_attempt) - 1

                break

        # ---- Attempt-level global attribution ----
        if not all_matched and first_failed_stage_idx is not None:
            # Seats checked BEFORE the first failure → "globally impacted (other)"
            for s in checked_seats_in_attempt[:first_failed_stage_idx]:
                seat_fail_global_other[s] = (
                    seat_fail_global_other.get(s, 0) + 1
                )

            # Seats NOT checked because we broke early → "globally unchecked"
            checked_set = set(checked_seats_in_attempt)
            for s in processing_order:
                sp = profile.seat_profiles.get(s)
                if not isinstance(sp, SeatProfile) or not sp.subprofiles:
                    continue
                if s not in checked_set:
                    seat_fail_global_unchecked[s] = (
                        seat_fail_global_unchecked.get(s, 0) + 1
                    )

            # Fire per-attempt debug hook (copies to prevent mutation).
            if _dg._DEBUG_ON_ATTEMPT_FAILURE_ATTRIBUTION is not None:
                try:
                    _dg._DEBUG_ON_ATTEMPT_FAILURE_ATTRIBUTION(
                        profile,
                        board_number,
                        board_attempts,
                        dict(seat_fail_as_seat),
                        dict(seat_fail_global_other),
                        dict(seat_fail_global_unchecked),
                        dict(seat_fail_hcp),
                        dict(seat_fail_shape),
                    )
                except Exception as exc:
                    print(f"WARNING: debug hook failed: {exc}", file=sys.stderr)

        if all_matched:
            # Fire debug_board_stats callback on success.
            if debug_board_stats is not None:
                debug_board_stats(dict(seat_fail_counts), dict(seat_seen_counts))
            return Deal(
                board_number=board_number,
                dealer=profile.dealer,
                vulnerability=_vulnerability_for_board(board_number),
                hands=hands,
            )

    # Exhausted all attempts — fire hooks before raising.
    if debug_board_stats is not None:
        debug_board_stats(dict(seat_fail_counts), dict(seat_seen_counts))

    if _dg._DEBUG_ON_MAX_ATTEMPTS is not None:
        try:
            viability_summary = _compute_viability_summary(
                seat_fail_counts=seat_fail_counts,
                seat_seen_counts=seat_seen_counts,
            )
            _dg._DEBUG_ON_MAX_ATTEMPTS(
                profile,
                board_number,
                board_attempts,
                dict(chosen_indices),
                dict(seat_fail_counts),
                viability_summary,
            )
        except Exception as exc:
            print(f"WARNING: debug hook failed: {exc}", file=sys.stderr)

    raise DealGenerationError(
        f"v2: Failed to construct constrained deal for board {board_number} "
        f"after {_max_attempts} attempts."
    )
