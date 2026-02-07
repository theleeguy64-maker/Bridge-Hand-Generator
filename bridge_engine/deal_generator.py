# bridge_engine/deal_generator.py
from __future__ import annotations

from typing import Callable, Dict, List, Optional, Tuple, Any

import math
import random
import time

from .setup_env import SetupResult
from .hand_profile import (
    HandProfile,
    SeatProfile,
    SubProfile,
    StandardSuitConstraints,
    RandomSuitConstraintData,
    PartnerContingentData,
)
from .seat_viability import _match_seat
from .profile_viability import _cross_seat_feasible

# ---------------------------------------------------------------------------
# Re-export types, constants, dataclasses, exception, and debug hooks from
# deal_generator_types so that existing callers (import dg; dg.Deal, dg.MAX_BOARD_ATTEMPTS, etc.)
# continue to work unchanged.
# ---------------------------------------------------------------------------
from .deal_generator_types import *   # noqa: F401,F403
from .deal_generator_types import (   # explicit re-imports for linters / IDE
    Seat, Card, SeatFailCounts, SeatSeenCounts,
    DealGenerationError,
    Deal, DealSet, SuitAnalysis,
    HardestSeatConfig, _HARDEST_SEAT_CONFIG,
    MAX_BOARD_ATTEMPTS, MAX_ATTEMPTS_HAND_2_3, MIN_ATTEMPTS_FOR_UNVIABLE_CHECK,
    ROTATE_PROBABILITY, VULNERABILITY_SEQUENCE, ROTATE_MAP,
    SHAPE_PROB_GTE, SHAPE_PROB_THRESHOLD, PRE_ALLOCATE_FRACTION,
    RS_REROLL_INTERVAL, SUBPROFILE_REROLL_INTERVAL,
    RS_PRE_ALLOCATE_HCP_RETRIES, RS_PRE_ALLOCATE_FRACTION,
    MAX_BOARD_RETRIES, RESEED_TIME_THRESHOLD_SECONDS, MAX_SUBPROFILE_FEASIBILITY_RETRIES,
    CONSTRUCTIVE_MAX_SUM_MIN_CARDS,
    ENABLE_HCP_FEASIBILITY_CHECK, HCP_FEASIBILITY_NUM_SD, DEBUG_SECTION_C,
    _MASTER_DECK, _CARD_HCP,
    _DEBUG_ON_MAX_ATTEMPTS, _DEBUG_STANDARD_CONSTRUCTIVE_USED,
    _DEBUG_ON_ATTEMPT_FAILURE_ATTRIBUTION,
)

# Re-export shared helpers so existing callers (dg._card_hcp, etc.) still work.
from .deal_generator_helpers import *   # noqa: F401,F403
from .deal_generator_helpers import (   # explicit re-imports for linters / IDE
    _compute_viability_summary, _summarize_profile_viability,
    _is_unviable_bucket, _weighted_choice_index, classify_viability,
    _weights_for_seat_profile, _choose_index_for_seat,
    _build_deck, _get_constructive_mode,
    _HCP_BY_RANK, _card_hcp, _deck_hcp_stats, _check_hcp_feasibility,
    _deal_single_board_simple, _apply_vulnerability_and_rotation,
)






# ---------------------------------------------------------------------------
# Hardest-seat selection helpers (used by constrained deal builder)
# ---------------------------------------------------------------------------


def _seat_has_nonstandard_constraints(profile: HandProfile, seat: Seat) -> bool:
    """
    Return True if this seat has any non-standard constraints
    (Random Suit, Partner-Contingent, Opponents-Contingent).

    This is intentionally duck-typed so tests can use DummySeatProfile /
    DummySubprofile without importing the real SeatProfile type.
    """
    sp = profile.seat_profiles.get(seat)
    if sp is None:
        return False

    subprofiles = getattr(sp, "subprofiles", None)
    if not subprofiles:
        # Unconstrained seat or legacy profile without subprofiles.
        return False

    for sub in subprofiles:
        if (
            getattr(sub, "random_suit_constraint", None) is not None
            or getattr(sub, "partner_contingent_constraint", None) is not None
            or getattr(sub, "opponents_contingent_suit_constraint", None) is not None
        ):
            return True
    return False


def _is_shape_dominant_failure(
    seat: Seat,
    seat_fail_hcp: Dict[Seat, int],
    seat_fail_shape: Dict[Seat, int],
    min_shape_ratio: float,
) -> bool:
    """
    Return True if the seat's failures are shape-dominant (constructive can help).
    Return False if HCP-dominant (constructive won't help).

    Constructive sampling can guarantee shape (card counts per suit), but cannot
    guarantee HCP. So if a seat is failing mostly due to HCP constraints, using
    constructive help won't be effective.

    Args:
        seat: The seat to check.
        seat_fail_hcp: Per-seat HCP failure counter.
        seat_fail_shape: Per-seat shape failure counter.
        min_shape_ratio: Minimum shape_fails / (hcp_fails + shape_fails) ratio
                         required to consider constructive help useful.

    Returns:
        True if shape-dominant or insufficient data (benefit of the doubt).
        False if HCP-dominant.
    """
    hcp_fails = seat_fail_hcp.get(seat, 0)
    shape_fails = seat_fail_shape.get(seat, 0)
    total_classified = hcp_fails + shape_fails

    # No classified failures yet - give constructive benefit of the doubt.
    if total_classified == 0:
        return True

    shape_ratio = shape_fails / float(total_classified)
    return shape_ratio >= min_shape_ratio





def _choose_hardest_seat_for_board(
    profile: HandProfile,
    seat_fail_counts: Dict[Seat, int],
    seat_seen_counts: Dict[Seat, int],
    dealing_order: List[Seat],
    attempt_number: int,
    cfg: HardestSeatConfig,
) -> Optional[Seat]:
    """
    Choose the "hardest" seat for the current board, based on per-seat
    failure statistics.

    This helper is *pure* – it does not deal cards or mutate profile.
    It is safe to call even when we end up not using the result.
    """
    # Invariants-safety profiles never get "help" – they use the fast path.
    if getattr(profile, "is_invariants_safety_profile", False):
        return None

    # Don’t try to pick a hardest seat until we’re past the configured threshold.
    if attempt_number < cfg.min_attempts_before_help:
        return None

    # Filter to seats with enough failures and at least one attempted match.
    candidates: List[Seat] = [
        seat
        for seat, fails in seat_fail_counts.items()
        if fails >= cfg.min_fail_count_for_help
        and seat_seen_counts.get(seat, 0) > 0
    ]
    if not candidates:
        return None

    scores: Dict[Seat, float] = {}
    for seat in candidates:
        fails = seat_fail_counts[seat]
        seen = seat_seen_counts.get(seat, 0)
        if seen <= 0:
            continue

        rate = fails / float(seen)
        if rate < cfg.min_fail_rate_for_help:
            continue

        # Base score: failure rate, with a small bump for absolute fail count.
        score = rate + 0.01 * min(fails, 100)

        # Prefer seats with non-standard constraints if configured to do so.
        if cfg.prefer_nonstandard_seats and _seat_has_nonstandard_constraints(profile, seat):
            score += 0.05

        scores[seat] = score

    if not scores:
        return None

    best_score = max(scores.values())
    best_seats = [s for s, sc in scores.items() if sc == best_score]

    # Tie-break deterministically using dealing_order.
    for seat in dealing_order:
        if seat in best_seats:
            return seat

    # Fallback – should be unreachable if dealing_order is consistent.
    return None
    

def _build_single_board_random_suit_w_only(
    rng: random.Random,
    profile: HandProfile,
    board_number: int,
) -> "Deal":
    """
    Test-only helper for the Random Suit W + Partner Contingent E profile.

    This builds a single board where we only enforce West's Random Suit
    constraint via _match_seat. Other seats are unconstrained in this path.

    Used by generate_deals for the special test profile 'Test_RandomSuit_W_PC_E'
    so that tests which only assert West's Random Suit behaviour remain fast and
    robust without needing the full-table RS+PC constraints to be satisfied.
    """
    dealing_order: List[Seat] = list(profile.hand_dealing_order)

    west_sp = profile.seat_profiles.get("W")
    if not isinstance(west_sp, SeatProfile) or not west_sp.subprofiles:
        # Defensive: if the profile doesn't actually have a constrained West,
        # just fall back to the normal constrained pipeline.
        return _build_single_constrained_deal(
            rng=rng,
            profile=profile,
            board_number=board_number,
        )

    attempts = 0
    while attempts < MAX_BOARD_ATTEMPTS:
        attempts += 1

        # Deal a full deck according to the profile's dealing order.
        deck = _build_deck()
        rng.shuffle(deck)

        hands: Dict[Seat, List[Card]] = {}
        deck_idx = 0
        for seat in dealing_order:
            hand = deck[deck_idx : deck_idx + 13]
            deck_idx += 13
            hands[seat] = hand

        # Shared Random Suit choices for this board (used by RS / OC / PC).
        random_suit_choices: Dict[Seat, List[str]] = {}

        # Choose West's subprofile index using the same weighting logic as
        # the main constrained generator.
        idx0 = _choose_index_for_seat(rng, west_sp)
        chosen_sub = west_sp.subprofiles[idx0]

        matched, _chosen_rs, _ = _match_seat(
            profile=profile,
            seat="W",
            hand=hands["W"],
            seat_profile=west_sp,
            chosen_subprofile=chosen_sub,
            chosen_subprofile_index_1based=idx0 + 1,
            random_suit_choices=random_suit_choices,
            rng=rng,
        )

        if matched:
            # We know West satisfies its RS constraints; we don't enforce
            # anything on the other seats in this special test path.
            idx = (board_number - 1) % len(VULNERABILITY_SEQUENCE)
            vulnerability = VULNERABILITY_SEQUENCE[idx]
            return Deal(
                board_number=board_number,
                dealer=profile.dealer,
                vulnerability=vulnerability,
                hands=hands,
            )

    raise DealGenerationError(
        "Failed to construct Random-Suit-W-only board for "
        f"board {board_number} after {MAX_BOARD_ATTEMPTS} attempts."
    )


def _extract_standard_suit_minima(
    profile: Any,
    seat: Seat,
    chosen_subprofile: Any,
) -> Dict[str, int]:
    """
    Best-effort extraction of standard suit minima for a given seat.

    This is deliberately duck-typed so that:
      * real HandProfile / SeatProfile / SubProfile objects work, and
      * tests can use simple dummy objects.

    Returns a mapping from suit letter ("S", "H", "D", "C") to min_cards.
    Empty dict => no usable minima found.
    """

    def _from_suit_ranges(suit_ranges: Any) -> Dict[str, int]:
        mins: Dict[str, int] = {}
        if not suit_ranges:
            return mins

        def _record(suit_key: Any, entry: Any) -> None:
            min_cards = getattr(entry, "min_cards", None)
            if min_cards is None:
                return
            try:
                m = int(min_cards)
            except (TypeError, ValueError):
                return
            if m <= 0:
                return

            suit = None
            if isinstance(suit_key, str):
                suit = suit_key
            if not suit:
                suit = getattr(entry, "suit", None) or getattr(
                    entry, "suit_name", None
                )
            if isinstance(suit, str):
                s = suit[0].upper()
                if s in ("S", "H", "D", "C"):
                    mins[s] = m

        # Dict-like mapping?
        if isinstance(suit_ranges, dict):
            for key, entry in suit_ranges.items():
                _record(key, entry)
            return mins

        # Fallback: assume iterable of entries.
        try:
            for entry in suit_ranges:
                _record(None, entry)
        except TypeError:
            # Not actually iterable – ignore.
            return {}

        return mins

    # 1) Chosen subprofile's own standard constraints.
    if chosen_subprofile is not None:
        std = getattr(chosen_subprofile, "standard_constraints", None)
        if std is not None:
            mins = _from_suit_ranges(getattr(std, "suit_ranges", None))
            if mins:
                return mins

    # 2) SeatProfile-level constraints.
    seat_profiles = getattr(profile, "seat_profiles", None)
    seat_profile = None
    if isinstance(seat_profiles, dict):
        seat_profile = seat_profiles.get(seat)

    if seat_profile is not None:
        # 2a) Direct suit_ranges on the seat profile.
        mins = _from_suit_ranges(getattr(seat_profile, "suit_ranges", None))
        if mins:
            return mins

        # 2b) Nested standard_constraints on the seat profile.
        std_sp = getattr(seat_profile, "standard_constraints", None)
        if std_sp is not None:
            mins = _from_suit_ranges(getattr(std_sp, "suit_ranges", None))
            if mins:
                return mins

    # 3) Top-level profile.standard_constraints[seat].
    all_std = getattr(profile, "standard_constraints", None)
    if isinstance(all_std, dict):
        seat_std = all_std.get(seat)
        if seat_std is not None:
            mins = _from_suit_ranges(getattr(seat_std, "suit_ranges", None))
            if mins:
                return mins

    return {}


def _construct_hand_for_seat(
    rng: random.Random,
    deck: List[Card],
    min_suit_counts: Dict[str, int],
) -> List[Card]:
    """
    Construct a 13-card hand from `deck` that satisfies the given minimum
    suit counts. Mutates `deck` by removing the selected cards.

    This helper is intentionally simple and *only* used when constructive
    help is enabled and the minima are "reasonable".
    """
    # Defensive: if somehow we don't have enough cards, just take whatever is left.
    if len(deck) < 13:
        hand = list(deck)
        deck.clear()
        return hand

    def suit_of(card: Card) -> str:
        # Cards are simple strings like "AS", "TD", etc.
        s = str(card)
        return s[-1].upper() if s else ""

    hand: List[Card] = []

    # Phase 1 – satisfy minima per suit.
    for suit, required in min_suit_counts.items():
        if required <= 0:
            continue

        available = [c for c in deck if suit_of(c) == suit]
        if not available:
            continue

        if required > len(available):
            required = len(available)

        chosen = rng.sample(available, required)
        hand.extend(chosen)
        # O(n) removal using set lookup instead of O(n²) list.remove()
        chosen_set = set(chosen)
        deck[:] = [c for c in deck if c not in chosen_set]

    # Phase 2 – fill up to 13 cards from whatever remains.
    remaining_needed = 13 - len(hand)
    if remaining_needed > 0 and deck:
        if remaining_needed > len(deck):
            remaining_needed = len(deck)
        extra = rng.sample(deck, remaining_needed)
        hand.extend(extra)
        # O(n) removal using set lookup instead of O(n²) list.remove()
        extra_set = set(extra)
        deck[:] = [c for c in deck if c not in extra_set]

    return hand


# ---------------------------------------------------------------------------
# v2 shape-based help system helpers
# ---------------------------------------------------------------------------


def _dispersion_check(
    chosen_subprofiles: Dict[Seat, "SubProfile"],
    threshold: float = SHAPE_PROB_THRESHOLD,
    rs_pre_selections: Optional[Dict[Seat, List[str]]] = None,
) -> set:
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

            # Build the effective ranges for the pre-selected suits,
            # respecting pair_overrides for 2-suit RS.
            ranges_by_suit: Dict[str, object] = {}
            if (
                rs.required_suits_count == 2
                and rs.pair_overrides
                and len(pre_suits) == 2
            ):
                sorted_pair = tuple(sorted(pre_suits))
                matched_override = None
                for po in rs.pair_overrides:
                    if tuple(sorted(po.suits)) == sorted_pair:
                        matched_override = po
                        break
                if matched_override is not None:
                    ranges_by_suit[matched_override.suits[0]] = (
                        matched_override.first_range
                    )
                    ranges_by_suit[matched_override.suits[1]] = (
                        matched_override.second_range
                    )
                else:
                    for idx, suit in enumerate(pre_suits):
                        if idx < len(rs.suit_ranges):
                            ranges_by_suit[suit] = rs.suit_ranges[idx]
            else:
                for idx, suit in enumerate(pre_suits):
                    if idx < len(rs.suit_ranges):
                        ranges_by_suit[suit] = rs.suit_ranges[idx]

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
        # Resolve effective ranges (respecting pair_overrides).
        ranges_by_suit: Dict[str, object] = {}
        if (
            rs.required_suits_count == 2
            and rs.pair_overrides
            and len(rs_pre_selected) == 2
        ):
            sorted_pair = tuple(sorted(rs_pre_selected))
            matched = None
            for po in rs.pair_overrides:
                if tuple(sorted(po.suits)) == sorted_pair:
                    matched = po
                    break
            if matched is not None:
                ranges_by_suit[matched.suits[0]] = matched.first_range
                ranges_by_suit[matched.suits[1]] = matched.second_range
            else:
                for idx, suit in enumerate(rs_pre_selected):
                    if idx < len(rs.suit_ranges):
                        ranges_by_suit[suit] = rs.suit_ranges[idx]
        else:
            for idx, suit in enumerate(rs_pre_selected):
                if idx < len(rs.suit_ranges):
                    ranges_by_suit[suit] = rs.suit_ranges[idx]

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
) -> List[Card]:
    """
    Fill n cards from a shuffled deck, skipping cards that would bust
    a suit maximum or push total HCP over the maximum.  Skipped cards
    remain in the deck for other seats.

    Since the deck is already shuffled, walking front-to-back and
    accepting/skipping is equivalent to random selection with rejection.

    Args:
        deck: Shuffled deck (mutable, modified in place).
        n: Number of cards to fill.
        pre_cards: Cards already in hand (pre-allocated), used to count
            current suit holdings and HCP.
        suit_maxima: Max cards per suit {S: max, H: max, D: max, C: max}.
        total_max_hcp: Maximum total HCP for the hand (default 40 = no limit).

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

        accepted.append(card)
        suit_count[suit] += 1
        current_hcp += card_hcp

    deck[:] = remaining
    return accepted


# ---------------------------------------------------------------------------
# HCP feasibility utilities (TODO #5)
#
# These functions support early rejection of hands whose pre-allocated cards
# make the target HCP range statistically implausible.  The check runs after
# shape pre-allocation but before the random fill, saving the cost of dealing
# HCP utilities (_card_hcp, _deck_hcp_stats, _check_hcp_feasibility) are
# imported from deal_generator_helpers (re-exported via *)

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
        fraction: Fraction of minima to pre-allocate (default 0.50).

    Returns:
        List of pre-allocated cards (may be empty).
    """
    import math

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
        fraction: Fraction of minima to pre-allocate (default 0.50).

    Returns:
        List of pre-allocated cards (may be empty).
    """
    import math

    rs = getattr(subprofile, "random_suit_constraint", None)
    if rs is None:
        return []

    # Build the effective ranges for each pre-selected suit,
    # respecting pair_overrides for 2-suit RS.
    ranges_by_suit: Dict[str, object] = {}
    if (
        rs.required_suits_count == 2
        and rs.pair_overrides
        and len(pre_selected_suits) == 2
    ):
        sorted_pair = tuple(sorted(pre_selected_suits))
        matched_override = None
        for po in rs.pair_overrides:
            if tuple(sorted(po.suits)) == sorted_pair:
                matched_override = po
                break
        if matched_override is not None:
            ranges_by_suit[matched_override.suits[0]] = (
                matched_override.first_range
            )
            ranges_by_suit[matched_override.suits[1]] = (
                matched_override.second_range
            )
        else:
            for idx, suit in enumerate(pre_selected_suits):
                if idx < len(rs.suit_ranges):
                    ranges_by_suit[suit] = rs.suit_ranges[idx]
    else:
        for idx, suit in enumerate(pre_selected_suits):
            if idx < len(rs.suit_ranges):
                ranges_by_suit[suit] = rs.suit_ranges[idx]

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
    if ENABLE_HCP_FEASIBILITY_CHECK and pre_allocated:
        # Compute deck HCP stats from known full-deck constants
        # minus what was removed by pre-allocation.
        removed_hcp_sum = 0
        removed_hcp_sum_sq = 0
        for cards in pre_allocated.values():
            for c in cards:
                v = _CARD_HCP[c]
                removed_hcp_sum += v
                removed_hcp_sum_sq += v * v
        deck_hcp_sum = 40 - removed_hcp_sum
        deck_hcp_sum_sq = 120 - removed_hcp_sum_sq
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
                    HCP_FEASIBILITY_NUM_SD,
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
                # Constrained fill: skip cards that would bust suit max
                # or push total HCP over the maximum.
                rs_for_seat = (
                    rs_pre_selections.get(seat)
                    if rs_pre_selections else None
                )
                maxima = _get_suit_maxima(sub, rs_for_seat)
                std = getattr(sub, "standard", None)
                max_hcp = (
                    getattr(std, "total_max_hcp", 40)
                    if std is not None else 40
                )
                fill = _constrained_fill(
                    deck, remaining_needed, pre, maxima, max_hcp
                )
            else:
                fill = _random_deal(rng, deck, remaining_needed)
            hands[seat] = pre + fill

    return hands, None




# ---------------------------------------------------------------------------
# Subprofile selection (extracted from _build_single_constrained_deal closure
# so v2 can reuse it without duplication).
#
# NOTE: This function lives here (not in deal_generator_helpers) because it
# uses isinstance(x, SeatProfile) checks, and several tests monkeypatch
# deal_generator.SeatProfile with dummy classes. Keeping it in this module
# ensures the isinstance checks resolve through the monkeypatchable name.
# ---------------------------------------------------------------------------

def _select_subprofiles_for_board(
    rng: random.Random,
    profile: HandProfile,
    dealing_order: List[Seat],
) -> Tuple[Dict[Seat, SubProfile], Dict[Seat, int]]:
    """
    Select a concrete subprofile index for each seat, with cross-seat
    feasibility rejection.

    NS:
      * If ns_index_coupling_enabled is True and both N/S have >1 subprofiles
        and equal lengths, use index coupling:
          - choose an NS "driver" (via ns_driver_seat or opener in dealing order),
          - pick its index by weights,
          - force responder to use same index.

    EW:
      * Always index-coupled when both E/W have >1 subprofiles and equal lengths,
        using the first EW seat in dealing_order as the driver.

    Any remaining seats just choose their own index by their local weights.

    After selecting, _cross_seat_feasible() checks whether the chosen
    combination can possibly succeed (HCP sums, per-suit card counts).
    If infeasible, we retry up to MAX_SUBPROFILE_FEASIBILITY_RETRIES times.
    If all retries are exhausted, the last selection is returned (the
    attempt loop will handle it, but this should be extremely rare).
    """

    def _pick_once() -> Tuple[Dict[Seat, SubProfile], Dict[Seat, int]]:
        """Single round of subprofile selection (no feasibility check)."""
        chosen_subprofiles: Dict[Seat, SubProfile] = {}
        chosen_indices: Dict[Seat, int] = {}

        # --- NS coupling logic ---------------------------------------------
        north_sp = profile.seat_profiles.get("N")
        south_sp = profile.seat_profiles.get("S")

        ns_coupling_enabled = bool(
            getattr(profile, "ns_index_coupling_enabled", True)
        )

        ns_coupling_possible = (
            ns_coupling_enabled
            and isinstance(north_sp, SeatProfile)
            and isinstance(south_sp, SeatProfile)
            and len(north_sp.subprofiles) > 1
            and len(south_sp.subprofiles) > 1
            and len(north_sp.subprofiles) == len(south_sp.subprofiles)
        )

        if ns_coupling_possible:
            # Determine NS driver seat.
            ns_driver: Optional[Seat] = profile.ns_driver_seat(rng)
            if ns_driver not in ("N", "S"):
                # Fall back to first NS seat in dealing order.
                ns_driver = next(
                    (s for s in dealing_order if s in ("N", "S")), "N"
                )

            ns_follower: Seat = "S" if ns_driver == "N" else "N"

            driver_sp = profile.seat_profiles.get(ns_driver)
            follower_sp = profile.seat_profiles.get(ns_follower)

            if isinstance(driver_sp, SeatProfile) and isinstance(
                follower_sp, SeatProfile
            ):
                idx = _choose_index_for_seat(rng, driver_sp)
                chosen_indices[ns_driver] = idx
                chosen_indices[ns_follower] = idx
                chosen_subprofiles[ns_driver] = driver_sp.subprofiles[idx]
                chosen_subprofiles[ns_follower] = follower_sp.subprofiles[idx]

        # --- EW coupling logic ---------------------------------------------
        east_sp = profile.seat_profiles.get("E")
        west_sp = profile.seat_profiles.get("W")

        ew_coupling_possible = (
            isinstance(east_sp, SeatProfile)
            and isinstance(west_sp, SeatProfile)
            and len(east_sp.subprofiles) > 1
            and len(west_sp.subprofiles) > 1
            and len(east_sp.subprofiles) == len(west_sp.subprofiles)
        )

        if ew_coupling_possible:
            # EW "driver" = first of E/W in dealing_order.
            ew_driver: Seat = next(
                (s for s in dealing_order if s in ("E", "W")), "E"
            )
            ew_follower: Seat = "W" if ew_driver == "E" else "E"

            driver_sp = profile.seat_profiles.get(ew_driver)
            follower_sp = profile.seat_profiles.get(ew_follower)

            if isinstance(driver_sp, SeatProfile) and isinstance(
                follower_sp, SeatProfile
            ):
                idx = _choose_index_for_seat(rng, driver_sp)
                chosen_indices[ew_driver] = idx
                chosen_indices[ew_follower] = idx
                chosen_subprofiles[ew_driver] = driver_sp.subprofiles[idx]
                chosen_subprofiles[ew_follower] = follower_sp.subprofiles[idx]

        # --- Remaining seats (incl. unconstrained or single-subprofile) ----
        for seat_name, seat_profile in profile.seat_profiles.items():
            if not isinstance(seat_profile, SeatProfile):
                continue
            if not seat_profile.subprofiles:
                # Unconstrained seat – nothing to select.
                continue
            if seat_name in chosen_indices:
                continue

            idx = _choose_index_for_seat(rng, seat_profile)
            chosen_indices[seat_name] = idx
            chosen_subprofiles[seat_name] = seat_profile.subprofiles[idx]

        return chosen_subprofiles, chosen_indices

    # --- Feasibility retry loop -------------------------------------------
    # Try up to MAX_SUBPROFILE_FEASIBILITY_RETRIES times to find a feasible
    # combination.  For easy profiles (all combos feasible) this always
    # succeeds on the first try — zero overhead.  For hard profiles like
    # "Defense to Weak 2s" (43.8% of N×E combos infeasible), this eliminates
    # all wasted 1000-attempt chunks on impossible combinations.
    for _ in range(MAX_SUBPROFILE_FEASIBILITY_RETRIES):
        chosen_subprofiles, chosen_indices = _pick_once()
        feasible, _reason = _cross_seat_feasible(chosen_subprofiles)
        if feasible:
            return chosen_subprofiles, chosen_indices

    # All retries exhausted — return last selection and let the attempt loop
    # handle it.  This should be extremely rare (only if ALL subprofile
    # combos are infeasible, which the validation-time check already flags).
    return chosen_subprofiles, chosen_indices


def _build_single_constrained_deal(
    rng: random.Random,
    profile: HandProfile,
    board_number: int,
    *,
    debug_board_stats: Optional[
        Callable[[SeatFailCounts, SeatSeenCounts], None]
    ] = None,
) -> "Deal":
    """
    Build a single constrained deal (Stage C1).

    This function:

      * chooses subprofiles (with NS / EW index coupling where applicable),
      * deals a full 52-card deck according to hand_dealing_order,
      * matches each hand against the selected subprofile via _match_seat,
      * retries up to MAX_BOARD_ATTEMPTS on failure,
      * returns a Deal on success or raises DealGenerationError if exhausted.
    """

    dealing_order: List[Seat] = list(profile.hand_dealing_order)

    def _vulnerability_for_board(n: int) -> str:
        """Simple cyclic vulnerability pattern."""
        idx = (n - 1) % len(VULNERABILITY_SEQUENCE)
        return VULNERABILITY_SEQUENCE[idx]

    # -------------------------------------------------------------------
    # FAST PATH: invariants-safety profiles
    #
    # Profiles tagged with is_invariants_safety_profile are used only as
    # safety nets (e.g. test_deal_invariants). For these, we *explicitly*
    # skip all constraint-matching and just deal well-formed random boards
    # respecting the profile's dealing_order.
    # -------------------------------------------------------------------
    if getattr(profile, "is_invariants_safety_profile", False):
        deck = _build_deck()
        rng.shuffle(deck)

        hands: Dict[Seat, List[Card]] = {}
        deck_idx = 0
        for seat in dealing_order:
            hand = deck[deck_idx : deck_idx + 13]
            deck_idx += 13
            hands[seat] = hand

        vulnerability = _vulnerability_for_board(board_number)
        return Deal(
            board_number=board_number,
            dealer=profile.dealer,
            vulnerability=vulnerability,
            hands=hands,
        )

    # -------------------------------------------------------------------
    # Full constrained path (for real constraint-bearing profiles)
    # -------------------------------------------------------------------

    # Decide which constructive modes are active for this profile.
    # (Note: the first assignment at the old line 1201 was dead code —
    #  always overwritten here before use.  Kept just one.)
    constructive_mode = _get_constructive_mode(profile)

    # -----------------------------------------------------------------------
    # Main board-attempt loop
    # -----------------------------------------------------------------------
    board_attempts = 0
    # Track which seat fails most often across attempts for this board.
    seat_fail_counts: Dict[Seat, int] = {}
    # Track how many times we've *tried* to match each seat this board.
    seat_seen_counts: Dict[Seat, int] = {}
    # Snapshot of the last attempt's chosen subprofile indices per seat.
    last_chosen_indices: Dict[Seat, int] = {}
    # NEW: per-board failure attribution counters
    seat_fail_as_seat: Dict[Seat, int] = {}
    seat_fail_global_other: Dict[Seat, int] = {}
    seat_fail_global_unchecked: Dict[Seat, int] = {}
    # NEW: breakdown of seat-level failures by cause (HCP vs shape)
    seat_fail_hcp: Dict[Seat, int] = {}
    seat_fail_shape: Dict[Seat, int] = {}
    while board_attempts < MAX_BOARD_ATTEMPTS:
        board_attempts += 1

        # Decide which seat, if any, looks "hardest" for this board.
        allow_std_constructive = constructive_mode["standard"]

        help_seat: Optional[Seat] = None
        if allow_std_constructive:
            help_seat = _choose_hardest_seat_for_board(
                profile=profile,
                seat_fail_counts=seat_fail_as_seat,  # <-- Step 1: local seat-level fails ONLY
                seat_seen_counts=seat_seen_counts,
                dealing_order=dealing_order,
                attempt_number=board_attempts,
                cfg=_HARDEST_SEAT_CONFIG,
            )
        # Choose subprofiles for this board (index-coupled where applicable).
        chosen_subprofiles, chosen_indices = _select_subprofiles_for_board(
            rng, profile, dealing_order
        )

        # Keep a snapshot of indices from this attempt for debug reporting.
        last_chosen_indices = dict(chosen_indices)

        # Build and shuffle a full deck.
        deck = _build_deck()
        rng.shuffle(deck)

        hands: Dict[Seat, List[Card]] = {}

        # --------------------------
        # Optional constructive path
        # --------------------------
        use_constructive = False
        constructive_minima: Dict[str, int] = {}

        # Compute current viability summary once per attempt so both the
        # debug hook and constructive help can share it.
        viability_summary = _summarize_profile_viability(
            seat_fail_counts,
            seat_seen_counts,
        )

        # P1.3: Early termination if any seat is unviable and we have enough data.
        # This prevents grinding to 10,000 attempts on hopeless profiles.
        if board_attempts >= MIN_ATTEMPTS_FOR_UNVIABLE_CHECK:
            unviable_seats = [
                seat for seat, bucket in viability_summary.items()
                if _is_unviable_bucket(bucket)
            ]
            if unviable_seats:
                raise DealGenerationError(
                    f"Profile declared unviable for board {board_number} after "
                    f"{board_attempts} attempts. Unviable seat(s): {unviable_seats}. "
                    f"These seats have >90% failure rate with sufficient attempts."
                )

        # Standard constructive help (v1 algorithm), allowed either by v1 mode or v2-on-std review mode.
        allow_std_constructive = constructive_mode["standard"] or constructive_mode.get("nonstandard_v2", False)

        # Constructive help (v1 algorithm), allowed either by v1 mode or v2-on-std review mode.
        # NOTE: we now allow constructive for *any* helper seat, standard or non-standard,
        # as long as we can derive sensible suit minima for that seat.
        allow_constructive = constructive_mode["standard"] or constructive_mode.get("nonstandard_v2", False)

        if allow_constructive and help_seat is not None:
            # Check if failures are shape-dominant before trying constructive.
            # If HCP-dominant, constructive help won't be effective (can't
            # pre-commit HCP, only card counts).
            if _is_shape_dominant_failure(
                seat=help_seat,
                seat_fail_hcp=seat_fail_hcp,
                seat_fail_shape=seat_fail_shape,
                min_shape_ratio=_HARDEST_SEAT_CONFIG.min_shape_ratio_for_constructive,
            ):
                constructive_minima = _extract_standard_suit_minima(
                    profile=profile,
                    seat=help_seat,
                    chosen_subprofile=chosen_subprofiles.get(help_seat),
                )
                total_min = sum(constructive_minima.values())
                if 0 < total_min <= CONSTRUCTIVE_MAX_SUM_MIN_CARDS:
                    use_constructive = True

                    if _DEBUG_STANDARD_CONSTRUCTIVE_USED is not None:
                        try:
                            _DEBUG_STANDARD_CONSTRUCTIVE_USED(
                                profile,
                                board_number,
                                board_attempts,
                                help_seat,
                            )
                        except Exception:
                            # Debug hooks must never affect deal generation.
                            pass
   
        if use_constructive and help_seat is not None:
            # Mutating deck: each hand draws from the remaining cards.
            working_deck = list(deck)

            for seat in dealing_order:
                if seat == help_seat:
                    hand = _construct_hand_for_seat(
                        rng=rng,
                        deck=working_deck,
                        min_suit_counts=constructive_minima,
                    )
                else:
                    # Plain random draw for the other seats from what's left.
                    take = min(13, len(working_deck))
                    hand = working_deck[:take]
                    del working_deck[:take]
                hands[seat] = hand
        else:
            # Original behaviour: just slice 13 cards per seat in order.
            deck_idx = 0
            for seat in dealing_order:
                hand = deck[deck_idx : deck_idx + 13]
                deck_idx += 13
                hands[seat] = hand

        # Shared Random Suit choices for this board (used by RS / OC / PC).
        random_suit_choices: Dict[Seat, List[str]] = {}

        # --------------------------------------------------------------
        # Match each seat's hand against its chosen subprofile.
        #
        # IMPORTANT: process Random-Suit seats *first*, so partner-
        # contingent seats can see their partner's RS choices in
        # random_suit_choices.
        # --------------------------------------------------------------
        all_matched = True

        rs_seats: List[Seat] = []
        other_seats: List[Seat] = []

        for seat in dealing_order:
            seat_profile = profile.seat_profiles.get(seat)
            if not isinstance(seat_profile, SeatProfile) or not seat_profile.subprofiles:
                continue

            chosen_sub = chosen_subprofiles.get(seat)
            if (
                chosen_sub is not None
                and getattr(chosen_sub, "random_suit_constraint", None) is not None
            ):
                rs_seats.append(seat)
            else:
                other_seats.append(seat)

        # Attempt-local “first failure” markers (seat-level failure only)
        first_failed_seat: Optional[Seat] = None
        first_failed_stage_idx: Optional[int] = None

        # Track constrained seats we actually *checked* this attempt, in order.
        checked_seats_in_attempt: List[Seat] = []

        # RS drivers first, then everything else (including PC / OC).
        processing_order = rs_seats + other_seats

        for seat in processing_order:
            seat_profile = profile.seat_profiles.get(seat)
            if not isinstance(seat_profile, SeatProfile) or not seat_profile.subprofiles:
                continue

            # We are attempting a match for this seat on this attempt.
            seat_seen_counts[seat] = seat_seen_counts.get(seat, 0) + 1
            checked_seats_in_attempt.append(seat)

            chosen_sub = chosen_subprofiles.get(seat)
            idx0 = chosen_indices.get(seat)

            # Defensive: if we didn't pick a subprofile, treat as seat-level failure.
            if chosen_sub is None or idx0 is None:
                matched = False
                chosen_rs = None
                fail_reason = "other"  # No subprofile to classify against
            else:
                # Match the seat against profile constraints
                matched, chosen_rs, fail_reason = _match_seat(
                    profile=profile,
                    seat=seat,
                    hand=hands[seat],
                    seat_profile=seat_profile,
                    chosen_subprofile=chosen_sub,
                    chosen_subprofile_index_1based=idx0 + 1,
                    random_suit_choices=random_suit_choices,
                    rng=rng,
                )

            # ---- Final seat-level failure decision for this seat ----
            if not matched:
                all_matched = False
                seat_fail_counts[seat] = seat_fail_counts.get(seat, 0) + 1

                # This seat is the first failing seat on this attempt.
                seat_fail_as_seat[seat] = seat_fail_as_seat.get(seat, 0) + 1

                # NEW: split that seat-level failure into HCP vs shape where possible.
                if fail_reason == "hcp":
                    seat_fail_hcp[seat] = seat_fail_hcp.get(seat, 0) + 1
                elif fail_reason == "shape":
                    seat_fail_shape[seat] = seat_fail_shape.get(seat, 0) + 1
                else:
                    # "other" (either we haven't wired the classifier yet,
                    # or the failure was some mixed/other reason).
                    pass

                # Record "first failure" markers (only once)
                if first_failed_seat is None:
                    first_failed_seat = seat
                    first_failed_stage_idx = len(checked_seats_in_attempt) - 1

                break

        # ---- Attempt-level global attribution (only when we failed due to a seat-level failure) ----
        if not all_matched and first_failed_stage_idx is not None:
            # Seats checked BEFORE the first failure are "globally impacted (other)"
            for s in checked_seats_in_attempt[:first_failed_stage_idx]:
                seat_fail_global_other[s] = seat_fail_global_other.get(s, 0) + 1

            # Seats NOT checked because we broke early are "globally unchecked"
            checked_set = set(checked_seats_in_attempt)
            for s in processing_order:
                sp = profile.seat_profiles.get(s)
                if not isinstance(sp, SeatProfile) or not sp.subprofiles:
                    continue
                if s not in checked_set:
                    seat_fail_global_unchecked[s] = seat_fail_global_unchecked.get(s, 0) + 1

            # NOW emit debug hook with complete attribution for this attempt
            if _DEBUG_ON_ATTEMPT_FAILURE_ATTRIBUTION is not None:
                try:
                    _DEBUG_ON_ATTEMPT_FAILURE_ATTRIBUTION(
                        profile,
                        board_number,
                        board_attempts,
                        dict(seat_fail_as_seat),
                        dict(seat_fail_global_other),
                        dict(seat_fail_global_unchecked),
                        dict(seat_fail_hcp),       # NEW
                        dict(seat_fail_shape),     # NEW
                    )
                except Exception:
                    pass
                                        
        if all_matched:
            if debug_board_stats is not None:
                debug_board_stats(dict(seat_fail_counts), dict(seat_seen_counts))

            vulnerability = _vulnerability_for_board(board_number)
            return Deal(
                board_number=board_number,
                dealer=profile.dealer,
                vulnerability=vulnerability,
                hands=hands,
            )
    # -------------------------------------------------------------------
    # Attempts exhausted for a real constrained profile.
    #
    # At this point we *do* want a loud failure so we can debug. The only
    # place we skip constraint matching is the invariants fast path at
    # the top of this function (is_invariants_safety_profile == True).
    # -------------------------------------------------------------------
    
    if debug_board_stats is not None:
        debug_board_stats(dict(seat_fail_counts), dict(seat_seen_counts))
                
    if _DEBUG_ON_MAX_ATTEMPTS is not None:
        try:
            viability_summary = _compute_viability_summary(
                seat_fail_counts=seat_fail_counts,
                seat_seen_counts=seat_seen_counts,
            )
            _DEBUG_ON_MAX_ATTEMPTS(
                profile,
                board_number,
                board_attempts,
                dict(last_chosen_indices),
                dict(seat_fail_counts),
                viability_summary,  # new argument
            )
        except Exception:
            # Debug hooks must never interfere with normal error reporting.
            pass

    raise DealGenerationError(
        f"Failed to construct constrained deal for board {board_number} "
        f"after {MAX_BOARD_ATTEMPTS} attempts."
    )
        
# ---------------------------------------------------------------------------
# v2 constrained deal builder (shape-based help system)
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
      - Pre-allocates 50% of suit minima for tight seats via _deal_with_help()
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
    dealing_order: List[Seat] = list(profile.hand_dealing_order)

    # ------------------------------------------------------------------
    # FAST PATH: invariants-safety profiles (same as v1)
    # ------------------------------------------------------------------
    if getattr(profile, "is_invariants_safety_profile", False):
        deck = _build_deck()
        rng.shuffle(deck)
        hands: Dict[Seat, List[Card]] = {}
        idx = 0
        for seat in dealing_order:
            hands[seat] = deck[idx : idx + 13]
            idx += 13
        vul_idx = (board_number - 1) % len(VULNERABILITY_SEQUENCE)
        return Deal(
            board_number=board_number,
            dealer=profile.dealer,
            vulnerability=VULNERABILITY_SEQUENCE[vul_idx],
            hands=hands,
        )

    # ------------------------------------------------------------------
    # Full constrained path
    # ------------------------------------------------------------------

    # Select subprofiles once per board (index-coupled where applicable).
    chosen_subprofiles, chosen_indices = _select_subprofiles_for_board(
        rng, profile, dealing_order
    )

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
    processing_order: List[Seat] = rs_seats + other_seats

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

    while board_attempts < MAX_BOARD_ATTEMPTS:
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
            chosen_subprofiles, chosen_indices = _select_subprofiles_for_board(
                rng, profile, dealing_order
            )
            rs_pre_selections = _pre_select_rs_suits(rng, chosen_subprofiles)
            tight_seats = _dispersion_check(
                chosen_subprofiles, rs_pre_selections=rs_pre_selections
            )
            # Rebuild processing order since RS seats may have changed.
            rs_seats = []
            other_seats = []
            for seat in dealing_order:
                sp = profile.seat_profiles.get(seat)
                if not isinstance(sp, SeatProfile) or not sp.subprofiles:
                    continue
                sub = chosen_subprofiles.get(seat)
                if sub and getattr(sub, "random_suit_constraint", None) is not None:
                    rs_seats.append(seat)
                else:
                    other_seats.append(seat)
            processing_order = rs_seats + other_seats

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
            if _DEBUG_ON_ATTEMPT_FAILURE_ATTRIBUTION is not None:
                try:
                    _DEBUG_ON_ATTEMPT_FAILURE_ATTRIBUTION(
                        profile,
                        board_number,
                        board_attempts,
                        dict(seat_fail_as_seat),
                        dict(seat_fail_global_other),
                        dict(seat_fail_global_unchecked),
                        dict(seat_fail_hcp),
                        dict(seat_fail_shape),
                    )
                except Exception:
                    pass  # Debug hooks must never interfere with generation.
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
            if _DEBUG_ON_ATTEMPT_FAILURE_ATTRIBUTION is not None:
                try:
                    _DEBUG_ON_ATTEMPT_FAILURE_ATTRIBUTION(
                        profile,
                        board_number,
                        board_attempts,
                        dict(seat_fail_as_seat),
                        dict(seat_fail_global_other),
                        dict(seat_fail_global_unchecked),
                        dict(seat_fail_hcp),
                        dict(seat_fail_shape),
                    )
                except Exception:
                    pass  # Debug hooks must never interfere with generation.

        if all_matched:
            # Fire debug_board_stats callback on success.
            if debug_board_stats is not None:
                debug_board_stats(dict(seat_fail_counts), dict(seat_seen_counts))
            vul_idx = (board_number - 1) % len(VULNERABILITY_SEQUENCE)
            return Deal(
                board_number=board_number,
                dealer=profile.dealer,
                vulnerability=VULNERABILITY_SEQUENCE[vul_idx],
                hands=hands,
            )

    # Exhausted all attempts — fire hooks before raising.
    if debug_board_stats is not None:
        debug_board_stats(dict(seat_fail_counts), dict(seat_seen_counts))

    if _DEBUG_ON_MAX_ATTEMPTS is not None:
        try:
            _DEBUG_ON_MAX_ATTEMPTS(
                profile,
                board_number,
                board_attempts,
                dict(chosen_indices),
                dict(seat_fail_counts),
                None,  # viability_summary (not computed in v2)
            )
        except Exception:
            pass  # Debug hooks must never interfere with error reporting.

    raise DealGenerationError(
        f"v2: Failed to construct constrained deal for board {board_number} "
        f"after {MAX_BOARD_ATTEMPTS} attempts."
    )




# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


# -----------------------------------------------------------------------------
# TEMPORARY TEST HOOKS / ESCAPE HATCHES (deal regeneration)
#
# 1) Profile "Test_RandomSuit_W_PC_E"
#    - generate_deals() currently routes this profile through
#      Random Suit constraint and relaxes full-table matching.
#    - This exists solely to satisfy Section C's Random Suit W + PC E tests,
#      while we stabilise the full Random Suit + Partner Contingent pipeline.
#    - TODO(deal-regenerator):
#        Replace this special-case with the normal constrained C1 pipeline
#        once RS + PC semantics and seat viability are fully implemented and
#        tested end-to-end.
#
# 2) Profile "Test profile" (deal_invariants smoke test)
#    - generate_deals() currently short-circuits the constrained path and
#      uses the simple _deal_single_board_simple() pipeline for this profile.
#    - This is purely to let test_deal_invariants.py exercise basic card
#      invariants without being blocked by constraint/viability issues.
#    - TODO(deal-regenerator):
#        Remove this special-case and make the invariants test run through
#        the real constrained C1 pipeline once it is robust for simple
#        standard-only profiles.
# -----------------------------------------------------------------------------


def generate_deals(
    setup: SetupResult,
    profile,
    num_deals: int,
    enable_rotation: bool = True,
) -> DealSet:
    """
    Generate a set of deals.

    If `profile` is a real HandProfile:
      • Use the full constrained C1 logic and C2 enrichment.

    If `profile` is not a HandProfile (e.g. tests using DummyProfile):
      • Fallback to simple random dealing as in the original implementation,
        seeded by SetupResult.seed.

    Raises
    ------
    DealGenerationError
        If num_deals is invalid or constraints cannot be satisfied.
    """
    if num_deals <= 0:
        raise DealGenerationError(f"num_deals must be positive, got {num_deals}.")

    # Default RNG: driven by the setup seed.
    rng = random.Random(setup.seed)

    # Fallback path for tests / dummy profiles
    if not isinstance(profile, HandProfile):
        dealer: Seat = getattr(profile, "dealer", "N")
        dealing_order_attr = getattr(
            profile,
            "hand_dealing_order",
            ["N", "E", "S", "W"],
        )
        dealing_order: List[Seat] = list(dealing_order_attr)

        deals: List[Deal] = []
        for board_number in range(1, num_deals + 1):
            deal = _deal_single_board_simple(
                rng=rng,
                board_number=board_number,
                dealer=dealer,
                dealing_order=dealing_order,
            )
            deals.append(deal)
        return DealSet(deals=deals)

    # ---------------------------------------------------------------
    # Special-case: Profiles opting into the lightweight RS-W-only path
    #
    # Profiles with use_rs_w_only_path=True bypass the full constrained
    # pipeline and use a lighter helper that only enforces West's Random
    # Suit constraint. This is useful for test profiles that don't need
    # the full matching pipeline.
    #
    # P1.1 refactor: Flag-based routing replaces magic profile name check.
    # ---------------------------------------------------------------
    if getattr(profile, "use_rs_w_only_path", False):
        deals: List[Deal] = []
        for board_number in range(1, num_deals + 1):
            deal = _build_single_board_random_suit_w_only(
                rng=rng,
                profile=profile,
                board_number=board_number,
            )
            deals.append(deal)

        deals = _apply_vulnerability_and_rotation(
            rng,
            deals,
            rotate=enable_rotation,
        )
        return DealSet(deals=deals)

    # -------------------------
    # Full constrained path
    # -------------------------
    #
    # Board-level retry: each board gets up to MAX_BOARD_RETRIES chances.
    # Each retry calls the v2 builder with a fresh RNG state (advanced by
    # the previous failed attempt's 10K+ random operations), giving it
    # different subprofile selections, RS suits, and random fills.
    # For easy profiles, every board succeeds on retry 1 (no overhead).
    # For hard profiles (e.g. "Defense to Weak 2s" at ~10% per-retry
    # success rate), 50 retries gives ~99.5% per-board success.
    try:
        deals: List[Deal] = []
        board_times: List[float] = []   # Per-board elapsed seconds
        reseed_count: int = 0           # Number of adaptive re-seeds

        for board_number in range(1, num_deals + 1):
            board_start = time.monotonic()
            deal = None
            last_exc: Optional[Exception] = None
            for _retry in range(MAX_BOARD_RETRIES):
                try:
                    deal = _build_single_constrained_deal_v2(
                        rng=rng,
                        profile=profile,
                        board_number=board_number,
                    )
                    break  # Board succeeded.
                except DealGenerationError as exc:
                    last_exc = exc

                    # Adaptive re-seeding: if this board is taking too long,
                    # the current RNG trajectory is probably unfavorable.
                    # Replace with a fresh random seed (OS entropy) and keep
                    # trying. The timer resets so the new seed gets a full
                    # time budget.
                    if RESEED_TIME_THRESHOLD_SECONDS > 0.0:
                        elapsed = time.monotonic() - board_start
                        if elapsed >= RESEED_TIME_THRESHOLD_SECONDS:
                            new_seed = random.SystemRandom().randint(
                                1, 2**31 - 1
                            )
                            rng = random.Random(new_seed)
                            reseed_count += 1
                            board_start = time.monotonic()

                    continue  # Retry with advanced (or fresh) RNG state.

            board_elapsed = time.monotonic() - board_start
            board_times.append(board_elapsed)

            if deal is None:
                raise DealGenerationError(
                    f"Failed to generate board {board_number} after "
                    f"{MAX_BOARD_RETRIES} retries of "
                    f"{MAX_BOARD_ATTEMPTS} attempts each."
                ) from last_exc
            deals.append(deal)

        deals = _apply_vulnerability_and_rotation(
            rng,
            deals,
            rotate=enable_rotation,
        )
        return DealSet(
            deals=deals,
            board_times=board_times,
            reseed_count=reseed_count,
        )
    except DealGenerationError:
        raise  # Pass through domain errors without wrapping.
    except Exception as exc:
        # Narrow scope catch-all, wrapped into domain error
        raise DealGenerationError(f"Failed to generate deals: {exc}") from exc
        
