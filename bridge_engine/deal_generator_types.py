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
    board_times: List[float] = field(default_factory=list)   # Per-board seconds
    reseed_count: int = 0                                     # Number of mid-run re-seeds


@dataclass(frozen=True)
class SuitAnalysis:
    cards_by_suit: Dict[str, List[Card]]
    hcp_by_suit: Dict[str, int]
    total_hcp: int


@dataclass(frozen=True)
class HardestSeatConfig:
    """
    Configuration for deciding when and for which seat we should try
    "helping" via constructive sampling.

    These names and semantics are chosen to match test_hardest_seat_selection.
    """
    # Do not even consider help until we've seen at least this many
    # seat-match attempts on the current board (sum over all seats).
    min_attempts_before_help: int = 50

    # A seat must have failed at least this many times to be eligible.
    min_fail_count_for_help: int = 3

    # And its failure rate (failures / attempts) must be at least this high.
    min_fail_rate_for_help: float = 0.7

    # When multiple candidates are tied on stats, optionally prefer seats
    # that have non-standard constraints (Random Suit / PC / OC).
    prefer_nonstandard_seats: bool = True

    # Minimum ratio of shape failures to total (hcp+shape) for constructive
    # to be considered useful. Below this threshold, the seat is "HCP-dominant"
    # and constructive help won't be effective. Set to 0.0 to disable this check.
    min_shape_ratio_for_constructive: float = 0.5


# Default thresholds used by _build_single_constrained_deal.
_HARDEST_SEAT_CONFIG: HardestSeatConfig = HardestSeatConfig()


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_BOARD_ATTEMPTS: int = 10000
MAX_ATTEMPTS_HAND_2_3: int = 1000

# P1.3: Minimum attempts before early termination for unviable profiles.
# Must have enough data for reliable viability classification before
# declaring a profile "too hard". The viability threshold is 90% failure
# rate with at least 5 failures (see _is_unviable_bucket).
MIN_ATTEMPTS_FOR_UNVIABLE_CHECK: int = 100

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
    0:  1.000,
    1:  0.987,
    2:  0.920,
    3:  0.710,
    4:  0.430,
    5:  0.189,
    6:  0.063,
    7:  0.021,
    8:  0.005,
    9:  0.001,
    10: 0.0002,
    11: 0.00002,
    12: 0.000001,
    13: 0.00000003,
}

# Probability threshold: seats with any suit at or below this probability
# are considered "tight" and eligible for shape pre-allocation help.
SHAPE_PROB_THRESHOLD: float = 0.19

# Fraction of suit minima to pre-allocate for tight seats.
# 50% balances helping enough vs not depleting the deck for other seats.
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

# For v1 constructive sampling, only use suit minima when the total is
# "reasonable" – we don't want to pre-commit too many cards.
CONSTRUCTIVE_MAX_SUM_MIN_CARDS: int = 11

# ---------------------------------------------------------------------------
# HCP feasibility check constants (TODO #5)
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

# Toggleable debug flag for Section C
DEBUG_SECTION_C: bool = False


# ---------------------------------------------------------------------------
# Pre-built master deck: avoids 52 string concatenations per attempt.
# _build_deck() returns a copy so callers can mutate freely.
# ---------------------------------------------------------------------------
_MASTER_DECK: List[Card] = [
    r + s for s in "SHDC" for r in "AKQJT98765432"
]


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
# _build_single_constrained_deal.
# Tests (and power users) can monkeypatch this with a callable that accepts:
#   (profile, board_number, attempts, chosen_indices, seat_fail_counts)
_DEBUG_ON_MAX_ATTEMPTS: Optional[Callable[..., None]] = None

# Debug hook: invoked when standard constructive help (v1) is actually used.
# Signature: (profile, board_number, attempt_number, help_seat) -> None
_DEBUG_STANDARD_CONSTRUCTIVE_USED = None

# Debug hook: per-attempt failure attribution
# Signature:
#   (profile, board_number, attempt_number,
#    seat_fail_as_seat, seat_fail_global_other, seat_fail_global_unchecked)
_DEBUG_ON_ATTEMPT_FAILURE_ATTRIBUTION = None
