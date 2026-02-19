# bridge_engine/deal_generator.py
#
# Facade module for the deal generation system.
#
# This module re-exports all public names from the sub-modules so that
# existing callers (import dg; dg.Deal, dg.MAX_BOARD_ATTEMPTS, etc.)
# continue to work unchanged.  The actual implementations live in:
#
#   deal_generator_types.py   — types, constants, dataclasses, debug hooks
#   deal_generator_helpers.py — shared utilities (viability, HCP, deck, etc.)
#   deal_generator_v2.py      — v2 shape-based help system (active path)
#
# This module retains:
#   _try_pair_coupling()              — coupling helper (uses monkeypatchable SeatProfile)
#   _select_subprofiles_for_board()   — must live here because tests
#       monkeypatch deal_generator.SeatProfile for isinstance checks
#   generate_deals()                  — public entry point
#
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import random
import time

from .setup_env import SetupResult
from .hand_profile import (
    HandProfile,
    SeatProfile,
    SubProfile,
)
from .seat_viability import _match_seat
from .profile_viability import _cross_seat_feasible

# ---------------------------------------------------------------------------
# Re-export ALL names from sub-modules via wildcard so that existing callers
# (import dg; dg.Deal, dg.SHAPE_PROB_GTE, etc.) continue to work unchanged.
#
# IMPORTANT: `import *` skips _-prefixed names (no __all__ in sub-modules).
# Every _-prefixed name accessed through this facade — by v2 late imports
# (`_dg._DEBUG_ON_MAX_ATTEMPTS`), by tests, or by this module's own code —
# MUST appear in the explicit re-import lists below.
# Non-underscore names (Deal, MAX_BOARD_ATTEMPTS, etc.) come through the
# wildcard and don't need explicit listing.
# ---------------------------------------------------------------------------
from .deal_generator_types import *  # noqa: F401,F403
from .deal_generator_types import (  # _-prefixed names for v2 late imports
    _DEBUG_ON_MAX_ATTEMPTS,
    _DEBUG_ON_ATTEMPT_FAILURE_ATTRIBUTION,
)

from .deal_generator_helpers import *  # noqa: F401,F403
from .deal_generator_helpers import (  # _-prefixed names for this module + tests
    _choose_index_for_seat,
    _card_hcp,
    _deck_hcp_stats,
    _check_hcp_feasibility,
    _build_deck,
    _weighted_choice_index,
    _compute_viability_summary,
    _deal_single_board_simple,
    _apply_vulnerability_and_rotation,
)

# v2 shape-based help system — extracted to deal_generator_v2.py (#7)
from .deal_generator_v2 import (
    _dispersion_check,
    _pre_select_rs_suits,
    _random_deal,
    _get_suit_maxima,
    _constrained_fill,
    _pre_allocate,
    _pre_allocate_rs,
    _deal_with_help,
    _build_single_constrained_deal_v2,
    _compute_dealing_order,
    _subprofile_constraint_type,
)

# ---------------------------------------------------------------------------
# Subprofile selection helpers.
#
# NOTE: These functions live here (not in deal_generator_helpers) because they
# use isinstance(x, SeatProfile) checks, and several tests monkeypatch
# deal_generator.SeatProfile with dummy classes. Keeping them in this module
# ensures the isinstance checks resolve through the monkeypatchable name.
# ---------------------------------------------------------------------------


def _try_pair_coupling(
    rng: random.Random,
    seat_profiles: Dict[str, SeatProfile],
    seat_a: Seat,
    seat_b: Seat,
    driver_seat: Seat,
    chosen_subprofiles: Dict[Seat, SubProfile],
    chosen_indices: Dict[Seat, int],
) -> None:
    """
    Index-couple two seats if both have >1 subprofile with equal lengths.

    Picks a single subprofile index for *driver_seat* (by weight) and forces
    the other seat to use the same index.  Mutates *chosen_subprofiles* and
    *chosen_indices* in place; does nothing if coupling preconditions fail.
    """
    sp_a = seat_profiles.get(seat_a)
    sp_b = seat_profiles.get(seat_b)

    if not (
        isinstance(sp_a, SeatProfile)
        and isinstance(sp_b, SeatProfile)
        and len(sp_a.subprofiles) > 1
        and len(sp_b.subprofiles) > 1
        and len(sp_a.subprofiles) == len(sp_b.subprofiles)
    ):
        return  # Coupling not possible.

    follower_seat: Seat = seat_b if driver_seat == seat_a else seat_a
    driver_sp = seat_profiles.get(driver_seat)
    follower_sp = seat_profiles.get(follower_seat)

    if isinstance(driver_sp, SeatProfile) and isinstance(follower_sp, SeatProfile):
        idx = _choose_index_for_seat(rng, driver_sp)
        chosen_indices[driver_seat] = idx
        chosen_indices[follower_seat] = idx
        chosen_subprofiles[driver_seat] = driver_sp.subprofiles[idx]
        chosen_subprofiles[follower_seat] = follower_sp.subprofiles[idx]


def _select_subprofiles_for_board(
    rng: random.Random,
    profile: HandProfile,
    dealing_order: List[Seat],
) -> Tuple[Dict[Seat, SubProfile], Dict[Seat, int]]:
    """
    Select a concrete subprofile index for each seat, with cross-seat
    feasibility rejection.

    NS:
      * If ns_role_mode is not "no_driver_no_index" and both N/S have >1
        subprofiles and equal lengths, use index coupling:
          - choose an NS "driver" (via ns_driver_seat or opener in dealing order),
          - pick its index by weights,
          - force responder to use same index.

    EW:
      * If ew_role_mode is set (not "no_driver_no_index") and both E/W have
        >1 subprofiles with equal lengths, use index coupling:
          - choose an EW "driver" (via ew_driver_seat or first EW in dealing order),
          - pick its index by weights,
          - force the other seat to use same index.

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

        # --- NS coupling ---
        # Enabled for all ns_role_mode values EXCEPT "no_driver_no_index".
        # getattr needed: tests use duck-typed DummyProfile without this field
        _ns_mode = getattr(profile, "ns_role_mode", None) or "no_driver_no_index"
        if _ns_mode != "no_driver_no_index":
            ns_driver: Optional[Seat] = profile.ns_driver_seat(rng)
            if ns_driver not in ("N", "S"):
                ns_driver = next((s for s in dealing_order if s in ("N", "S")), "N")
            _try_pair_coupling(
                rng,
                profile.seat_profiles,
                "N",
                "S",
                ns_driver,
                chosen_subprofiles,
                chosen_indices,
            )

        # --- EW coupling ---
        # Enabled for all ew_role_mode values EXCEPT "no_driver_no_index".
        # getattr needed: tests use duck-typed DummyProfile without this field
        _ew_mode = getattr(profile, "ew_role_mode", None) or "no_driver_no_index"
        if _ew_mode != "no_driver_no_index":
            ew_driver: Optional[Seat] = profile.ew_driver_seat(rng)
            if ew_driver not in ("E", "W"):
                ew_driver = next((s for s in dealing_order if s in ("E", "W")), "E")
            _try_pair_coupling(
                rng,
                profile.seat_profiles,
                "E",
                "W",
                ew_driver,
                chosen_subprofiles,
                chosen_indices,
            )

        # --- Remaining seats (incl. unconstrained or single-subprofile) ----
        for seat_name, seat_profile in profile.seat_profiles.items():
            if not isinstance(seat_profile, SeatProfile):
                continue
            if not seat_profile.subprofiles:
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
    chosen_subprofiles: Dict[Seat, SubProfile] = {}
    chosen_indices: Dict[Seat, int] = {}
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
# Public API
# ---------------------------------------------------------------------------


def generate_deals(
    setup: SetupResult,
    profile,
    num_deals: int,
    enable_rotation: bool = True,
) -> DealSet:
    """
    Generate a set of deals.

    If `profile` is a real HandProfile:
      - Use the full constrained v2 pipeline (shape help, HCP rejection, etc.).

    If `profile` is not a HandProfile (e.g. tests using DummyProfile):
      - Fallback to simple random dealing, seeded by SetupResult.seed.

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
        deals: List[Deal] = []  # type: ignore[no-redef]
        board_times: List[float] = []  # Per-board elapsed seconds
        reseed_count: int = 0  # Number of adaptive re-seeds

        for board_number in range(1, num_deals + 1):
            board_start = time.monotonic()
            deal: Optional[Deal] = None  # type: ignore[no-redef]
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
                            new_seed = random.SystemRandom().randint(1, 2**31 - 1)
                            rng = random.Random(new_seed)
                            reseed_count += 1
                            board_start = time.monotonic()

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
        raise DealGenerationError(f"Failed to generate deals: {exc}") from exc
