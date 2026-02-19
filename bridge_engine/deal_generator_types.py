# bridge_engine/deal_generator_types.py
#
# Types, constants, dataclasses, exception, and debug hooks extracted from
# deal_generator.py as part of the #7 refactor.
#
# This is a LEAF module — it has no bridge_engine imports.
# All other deal_generator_* modules import from here.
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

Seat = str
Card = str

SeatFailCounts = Dict[Seat, int]
SeatSeenCounts = Dict[Seat, int]


# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------


class DealGenerationError(Exception):
    """Raised when something goes wrong during deal generation."""


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Deal:
    board_number: int
    dealer: Seat
    vulnerability: str  # 'None', 'NS', 'EW', 'Both'
    hands: Dict[Seat, List[Card]]


@dataclass(frozen=True)
class DealSet:
    deals: List[Deal]
    board_times: List[float] = field(default_factory=list)  # Per-board seconds
    reseed_count: int = 0  # Number of mid-run re-seeds


@dataclass(frozen=True)
class SuitAnalysis:
    cards_by_suit: Dict[str, List[Card]]
    hcp_by_suit: Dict[str, int]
    total_hcp: int


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_BOARD_ATTEMPTS: int = 10000

ROTATE_PROBABILITY: float = 0.5

VULNERABILITY_SEQUENCE: List[str] = ["None", "NS", "EW", "Both"]

ROTATE_MAP: Dict[Seat, Seat] = {
    "N": "S",
    "S": "N",
    "E": "W",
    "W": "E",
}

# ---------------------------------------------------------------------------
# Shape probability table (v2 help system)
#
# P(random 13-card hand has >= N cards in one suit).
# Derived from hypergeometric distribution: X ~ Hypergeometric(N=52, K=13, n=13).
# Used by _dispersion_check() to identify tight seats needing shape help.
# ---------------------------------------------------------------------------
SHAPE_PROB_GTE: Dict[int, float] = {
    0: 1.000,
    1: 0.987,
    2: 0.920,
    3: 0.710,
    4: 0.430,
    5: 0.189,
    6: 0.063,
    7: 0.021,
    8: 0.005,
    9: 0.001,
    10: 0.0002,
    11: 0.00002,
    12: 0.000001,
    13: 0.00000003,
}

# Probability threshold: seats with any suit at or below this probability
# are considered "tight" and eligible for shape pre-allocation help.
SHAPE_PROB_THRESHOLD: float = 0.19

# Fraction of suit minima to pre-allocate for tight seats.
# 75% balances helping enough vs not depleting the deck for other seats.
PRE_ALLOCATE_FRACTION: float = 0.75

# How often (in attempts) to re-roll the RS suit pre-selections within a board.
# Re-rolling protects against "stuck with a bad suit choice" scenarios by
# trying different RS suit combinations across chunks of attempts.
RS_REROLL_INTERVAL: int = 500

# How often (in attempts) to re-select subprofiles within a board.
# This is critical for hard profiles where N/E have 4+ subprofiles each —
# some subprofile combos are much easier than others (e.g. 3/16 combos might
# be feasible while 13/16 are nearly impossible).  Re-selecting gives us
# multiple bites at finding a workable combo within the same board.
# Set to 0 to disable subprofile re-rolling.
SUBPROFILE_REROLL_INTERVAL: int = 1000

# Number of retry attempts when pre-allocating RS suit cards to find a
# sample whose HCP is on-track for the suit's HCP target.  This is a
# form of rejection sampling: try multiple random samples and pick the
# first whose pro-rated HCP lands in the target range.
# Set to 0 to disable HCP targeting (pure random pre-allocation).
RS_PRE_ALLOCATE_HCP_RETRIES: int = 10

# Fraction of RS suit minima to pre-allocate.  Set to 1.0 so that RS suits
# are fully populated at pre-allocation time with HCP targeting.  This
# avoids the random fill blindly adding cards that bust the RS suit's HCP
# window (e.g. W in "Defense to Weak 2s" needs 5-7 HCP in exactly 6 cards;
# pre-allocating only 4 left the remaining 2 to random fill, causing 89%
# of W failures).  Standard constraints still use PRE_ALLOCATE_FRACTION.
RS_PRE_ALLOCATE_FRACTION: float = 1.0

# Maximum retries when _select_subprofiles_for_board() picks an infeasible
# combination (e.g. sum(min_hcp) > 40).  Each retry re-rolls all subprofile
# indices while respecting NS/EW coupling.  For easy profiles (no dead subs),
# this loop costs nothing — the first selection is always feasible.
# For "Defense to Weak 2s" (43.8% of combos infeasible), this eliminates
# all wasted 1000-attempt chunks on impossible combinations.
MAX_SUBPROFILE_FEASIBILITY_RETRIES: int = 100

# Maximum number of full retries per board in generate_deals().
# Each retry calls the v2 builder with MAX_BOARD_ATTEMPTS attempts.
# Between retries, the RNG has advanced significantly, so subprofile
# selections, RS suits, and random fills will all be different.
# For easy profiles, every board succeeds on the first try (retry 1).
# For hard profiles (e.g. "Defense to Weak 2s"), multiple retries give
# multiple chances to find a workable subprofile + RS combination.
# Total budget per board = MAX_BOARD_RETRIES * MAX_BOARD_ATTEMPTS.
MAX_BOARD_RETRIES: int = 50

# Per-board wall-clock time budget (seconds) before adaptive re-seeding.
# If a board's retry loop exceeds this threshold, the RNG is replaced with
# a fresh random seed (via SystemRandom) to escape an unfavorable trajectory.
# The timer resets after each re-seed, so multiple re-seeds per board are
# possible.  Set to 0.0 to disable adaptive re-seeding entirely.
# 1.75s chosen because good seeds produce boards in 0.6-2.1s (avg ~1.2s);
# a board still running at 1.75s is likely on an unfavorable trajectory.
RESEED_TIME_THRESHOLD_SECONDS: float = 1.75

# ---------------------------------------------------------------------------
# Full-deck HCP constants (52-card deck)
# ---------------------------------------------------------------------------

# Sum of HCP across all 52 cards: 4 suits × (A=4 + K=3 + Q=2 + J=1) = 40.
FULL_DECK_HCP_SUM: int = 40

# Sum of squared HCP values: 4 suits × (16 + 9 + 4 + 1) = 120.
FULL_DECK_HCP_SUM_SQ: int = 120

# Maximum HCP achievable in a single 13-card hand (AKQJ × 4 suits minus 3
# spot cards = 37). Used as a "no real cap" sentinel in suit-level constraints.
MAX_HAND_HCP: int = 37

# ---------------------------------------------------------------------------
# Viability classification thresholds
# ---------------------------------------------------------------------------

# Minimum failure count before a seat can be classified as "unviable".
UNVIABLE_MIN_FAILS: int = 5

# Minimum failure rate (fails/seen) to classify as "unviable".
UNVIABLE_MIN_RATE: float = 0.9

# ---------------------------------------------------------------------------
# HCP feasibility check constants
# ---------------------------------------------------------------------------

# Gate flag for HCP feasibility rejection during pre-allocation.
# When True, early rejection skips hands whose pre-allocated cards make the
# target HCP range statistically implausible — saving futile matching attempts.
# Proven via 36 unit + integration tests (test_hcp_feasibility.py).
ENABLE_HCP_FEASIBILITY_CHECK: bool = True

# Number of standard deviations for the HCP feasibility confidence interval.
# At 1.0 SD, ~68% of outcomes fall within [ExpDown, ExpUp].  Rejecting outside
# this band means "even a 1-sigma-favourable outcome can't reach the target".
HCP_FEASIBILITY_NUM_SD: float = 1.0


# ---------------------------------------------------------------------------
# Pre-built master deck: avoids 52 string concatenations per attempt.
# _build_deck() returns a copy so callers can mutate freely.
# ---------------------------------------------------------------------------
_MASTER_DECK: List[Card] = [r + s for s in "SHDC" for r in "AKQJT98765432"]

# Pre-built HCP lookup for every card in the deck.
# Avoids per-call function overhead on the hot path (4.5M+ calls/run).
# A=4, K=3, Q=2, J=1, all others=0.
_CARD_HCP: Dict[str, int] = {card: {"A": 4, "K": 3, "Q": 2, "J": 1}.get(card[0], 0) for card in _MASTER_DECK}


# ---------------------------------------------------------------------------
# Debug hooks
#
# These are mutable module-level variables. Submodules that need to read them
# at call-time must import the MODULE (not the names) to ensure monkeypatching
# in tests is visible:
#   from . import deal_generator_types as _dgt
#   ... _dgt._DEBUG_ON_MAX_ATTEMPTS ...
# ---------------------------------------------------------------------------

# Optional debug hook invoked when MAX_BOARD_ATTEMPTS is exhausted in
# _build_single_constrained_deal_v2.
# Tests (and power users) can monkeypatch this with a callable that accepts:
#   (profile, board_number, attempts, chosen_indices, seat_fail_counts)
_DEBUG_ON_MAX_ATTEMPTS: Optional[Callable[..., None]] = None

# Debug hook: per-attempt failure attribution
# Signature:
#   (profile, board_number, attempt_number,
#    seat_fail_as_seat, seat_fail_global_other, seat_fail_global_unchecked,
#    seat_fail_hcp, seat_fail_shape)
_DEBUG_ON_ATTEMPT_FAILURE_ATTRIBUTION: Optional[Callable] = None
