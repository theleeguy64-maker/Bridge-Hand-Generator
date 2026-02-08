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
# v1 builder helpers — extracted to deal_generator_v1.py (#7 Batch 4B)
# ---------------------------------------------------------------------------
from .deal_generator_v1 import (
    _seat_has_nonstandard_constraints,
    _is_shape_dominant_failure,
    _choose_hardest_seat_for_board,
    _extract_standard_suit_minima,
    _construct_hand_for_seat,
    _build_single_board_random_suit_w_only,
    _build_single_constrained_deal,
)




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
        
