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
    _vulnerability_for_board,
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
            return Deal(
                board_number=board_number,
                dealer=profile.dealer,
                vulnerability=_vulnerability_for_board(board_number),
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
# v2 shape-based help system helpers — extracted to deal_generator_v2.py (#7)
# ---------------------------------------------------------------------------
from .deal_generator_v2 import (
    _dispersion_check, _pre_select_rs_suits, _random_deal,
    _get_suit_maxima, _constrained_fill,
    _pre_allocate, _pre_allocate_rs,
    _deal_with_help,
)




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
# v2 constrained deal builder — extracted to deal_generator_v2.py (#7)
# ---------------------------------------------------------------------------
from .deal_generator_v2 import _build_single_constrained_deal_v2




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
        
