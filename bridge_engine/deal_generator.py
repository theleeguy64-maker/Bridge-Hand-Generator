# bridge_engine/deal_generator.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Callable, Dict, List, Optional, Sequence, Tuple, Any

import random

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

Seat = str
Card = str

SeatFailCounts = Dict[Seat, int]
SeatSeenCounts = Dict[Seat, int]


def _compute_viability_summary(
    seat_fail_counts: SeatFailCounts,
    seat_seen_counts: SeatSeenCounts,
) -> Dict[Seat, Dict[str, object]]:
    """
    Diagnostic helper: summarise per-seat attempts/successes and viability.

    This is intended for tests and debug hooks. It does *not* influence the
    core deal-generation logic.
    """
    summary: Dict[Seat, Dict[str, object]] = {}

    for seat, attempts in seat_seen_counts.items():
        failures = seat_fail_counts.get(seat, 0)
        successes = max(0, attempts - failures)
        rate = float(successes) / attempts if attempts > 0 else 0.0

        summary[seat] = {
            "attempts": attempts,
            "successes": successes,
            "failures": failures,
            "success_rate": rate,
            "viability": classify_viability(successes, attempts),
        }

    return summary
    
    
def _summarize_profile_viability(
    seat_fail_counts: SeatFailCounts,
    seat_seen_counts: SeatSeenCounts,
) -> Dict[Seat, str]:
    """
    Summarise how 'viable' each seat looks based on observed failures vs attempts.

    This is a *runtime* heuristic used only for:
      - constructive-help gating, and
      - debug hooks / diagnostics.

    Buckets (purely heuristic, not user-facing API):

      - "unknown": no attempts yet.
      - "likely": fail rate is modest (< 0.5) or very few failures.
      - "borderline": noticeably high fail rate (>= 0.5) but not hopeless.
      - "unviable": consistently failing (very high fail rate with enough data).
    """
    summary: Dict[Seat, str] = {}

    # Consider any seat that has ever been seen or failed.
    seats = set(seat_fail_counts.keys()) | set(seat_seen_counts.keys())

    for seat in seats:
        seen = seat_seen_counts.get(seat, 0)
        fails = seat_fail_counts.get(seat, 0)

        if seen == 0:
            bucket = "unknown"
        else:
            rate = fails / float(seen)

            # Heuristic thresholds; these are intentionally conservative so that
            # we only mark a seat as "unviable" when it's clearly struggling.
            if fails >= 5 and rate >= 0.9:
                bucket = "unviable"
            elif rate >= 0.5:
                bucket = "borderline"
            else:
                bucket = "likely"

        summary[seat] = bucket

    return summary    
    
    
def _is_unviable_bucket(bucket: object) -> bool:
    """
    Helper for defensive viability checks.

    Accepts either the literal string "unviable" or an Enum / object whose
    string representation contains "unviable" (case-insensitive).
    """
    if bucket is None:
        return False
    text = str(bucket).lower()
    return "unviable" in text   
    
    
def _weighted_choice_index(rng: random.Random, weights: Sequence[float]) -> int:
    """
    Choose an index according to non-negative weights.

    We assume validate_profile has already enforced:
      • all weights >= 0
      • at most one decimal place
      • sum ~ 100 (normalised to exactly 100 by validation)

    Implementation: scale by 10 to avoid float boundary issues, then
    do a simple integer roulette-wheel selection.
    """
    scaled = [int(round(w * 10.0)) for w in weights]
    total = sum(scaled)
    if total <= 0:
        raise ValueError("Total weight must be > 0 for weighted choice.")

    threshold = rng.randrange(total)
    cumulative = 0
    for idx, w in enumerate(scaled):
        cumulative += w
        if threshold < cumulative:
            return idx
    # Fallback for any rounding edge case
    return len(scaled) - 1


# ---------------------------------------------------------------------------
# Types and constants
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
PRE_ALLOCATE_FRACTION: float = 0.50

# Toggleable debug flag for Section C
DEBUG_SECTION_C: bool = False

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

class DealGenerationError(Exception):
    """Raised when something goes wrong during deal generation."""


# ---------------------------------------------------------------------------
# Hardest-seat selection helpers (used by constrained deal builder)
# ---------------------------------------------------------------------------

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



def _shadow_probe_nonstandard_constructive(
    profile: HandProfile,
    board_number: int,
    attempt_number: int,
    chosen_indices: Dict[Seat, int],
    seat_fail_counts: SeatFailCounts,
    seat_seen_counts: SeatSeenCounts,
    viability_summary: Dict[Seat, str],
    rs_bucket_snapshot: Dict[Seat, Dict[str, int]],
) -> None:
    """
    Shadow-only probe for non-standard (e.g. Random-Suit / PC) constructive v2.

    This is intentionally a no-op unless:
      * ENABLE_CONSTRUCTIVE_HELP_NONSTANDARD is True, and
      * _DEBUG_NONSTANDARD_CONSTRUCTIVE_SHADOW is set to a callable.

    It must never affect real deal generation; it just forwards a snapshot
    of the current stats / buckets to the debug hook.
    """
    if _DEBUG_NONSTANDARD_CONSTRUCTIVE_SHADOW is None:
        return

    # Forward a snapshot to the debug hook.
    try:
        _DEBUG_NONSTANDARD_CONSTRUCTIVE_SHADOW(
            profile,
            board_number,
            attempt_number,
            dict(chosen_indices),
            dict(seat_fail_counts),
            dict(seat_seen_counts),
            dict(viability_summary),
            dict(rs_bucket_snapshot),  # <- yes, include the RS buckets here
        )
    except Exception:
        # Debug hooks must never interfere with normal deal generation.
        pass



def _nonstandard_constructive_v2_policy(
    *,
    profile: HandProfile,
    board_number: int,
    attempt_number: int,
    chosen_indices: Optional[Dict[Seat, int]] = None,
    seat_fail_counts: Optional[SeatFailCounts] = None,
    seat_seen_counts: Optional[SeatSeenCounts] = None,
    viability_summary: Optional[Dict[Seat, str]] = None,
    rs_bucket_snapshot: Optional[Dict[Seat, Dict[str, int]]] = None,
    constraint_flags: Optional[Dict[Seat, Dict[str, bool]]] = None,  # P1.2: per-seat RS/PC/OC flags
    subprofile_stats: Optional[Dict[Seat, Dict[int, Dict[str, int]]]] = None,  # P1.4: per-subprofile tracking
) -> Dict[str, object]:
    """Return policy hints for non-standard constructive help v2.

    Piece 0 seam: this is called when constructive_mode["nonstandard_v2"] is enabled.
    By default it returns an empty dict and must not affect deal-generation behaviour.

    Tests may monkeypatch _DEBUG_NONSTANDARD_CONSTRUCTIVE_V2_POLICY to observe calls.

    P1.2 addition: constraint_flags provides per-seat mapping of which constraint
    types (RS, PC, OC) are active on the chosen subprofile for each seat.

    P1.4 addition: subprofile_stats provides per-subprofile success/failure counts
    for smarter nudging decisions. Shape: {seat: {subprofile_idx: {"seen": N, "failed": M}}}
    """
    # Defensive gating: even if a caller invokes this directly, do not run
    # policy hooks unless v2 is actually enabled for this profile.
    # This guarantees invariants-safety profiles can never observe v2 hooks
    # even if a test or caller bypasses _build_single_constrained_deal.
    try:
        if not _get_constructive_mode(profile).get("nonstandard_v2", False):
            return {}
    except Exception:
        # If the profile doesn't have the expected fields for gating, treat as disabled.
        return {}

    hook = _DEBUG_NONSTANDARD_CONSTRUCTIVE_V2_POLICY
    if hook is None:
        return {}

    # Backwards-compat chain:
    # - P1.4 (10 args): includes subprofile_stats
    # - P1.2 (9 args): includes constraint_flags
    # - Piece 1 (8 args): no constraint_flags
    # - Piece 0 (3 args): minimal signature
    try:
        # P1.4: full signature with subprofile_stats
        result = hook(
            profile,
            board_number,
            attempt_number,
            dict(chosen_indices or {}),
            dict(seat_fail_counts or {}),
            dict(seat_seen_counts or {}),
            dict(viability_summary or {}),
            dict(rs_bucket_snapshot or {}),
            dict(constraint_flags or {}),
            {seat: dict(idx_stats) for seat, idx_stats in (subprofile_stats or {}).items()},
        )
    except TypeError:
        try:
            # P1.2: 9-arg signature (no subprofile_stats)
            result = hook(
                profile,
                board_number,
                attempt_number,
                dict(chosen_indices or {}),
                dict(seat_fail_counts or {}),
                dict(seat_seen_counts or {}),
                dict(viability_summary or {}),
                dict(rs_bucket_snapshot or {}),
                dict(constraint_flags or {}),
            )
        except TypeError:
            try:
                # Piece 1: 8-arg signature (no constraint_flags)
                result = hook(
                    profile,
                    board_number,
                    attempt_number,
                    dict(chosen_indices or {}),
                    dict(seat_fail_counts or {}),
                    dict(seat_seen_counts or {}),
                    dict(viability_summary or {}),
                    dict(rs_bucket_snapshot or {}),
                )
            except TypeError:
                # Piece 0: minimal 3-arg signature
                result = hook(profile, board_number, attempt_number)
    if result is None:
        return {}

    if not isinstance(result, Mapping):
        raise TypeError(
            "_DEBUG_NONSTANDARD_CONSTRUCTIVE_V2_POLICY must return a Mapping[str, object] or None"
        )

    # Materialise to a plain dict to prevent surprising mutation/aliasing.
    return dict(result)


def _build_constraint_flags_per_seat(
    chosen_subprofiles: Dict[Seat, "SubProfile"],
) -> Dict[Seat, Dict[str, bool]]:
    """
    Build a mapping of constraint type flags per seat.

    For each seat in chosen_subprofiles, returns which constraint types
    (RS, PC, OC) are active on the chosen subprofile. This allows the
    v2 policy seam to make constraint-aware decisions.

    Returns:
        {"N": {"has_rs": False, "has_pc": False, "has_oc": False}, ...}
    """
    flags: Dict[Seat, Dict[str, bool]] = {}
    for seat, sub in chosen_subprofiles.items():
        flags[seat] = {
            "has_rs": getattr(sub, "random_suit_constraint", None) is not None,
            "has_pc": getattr(sub, "partner_contingent_constraint", None) is not None,
            "has_oc": getattr(sub, "opponents_contingent_suit_constraint", None) is not None,
        }
    return flags


# Default thresholds used by _build_single_constrained_deal.
_HARDEST_SEAT_CONFIG: HardestSeatConfig = HardestSeatConfig()

# For v1 constructive sampling, only use suit minima when the total is
# "reasonable" – we don't want to pre-commit too many cards.
CONSTRUCTIVE_MAX_SUM_MIN_CARDS: int = 11
    
    
@dataclass(frozen=True)
class Deal:
    board_number: int
    dealer: Seat
    vulnerability: str  # 'None', 'NS', 'EW', 'Both'
    hands: Dict[Seat, List[Card]]


@dataclass(frozen=True)
class DealSet:
    deals: List[Deal]


@dataclass(frozen=True)
class SuitAnalysis:
    cards_by_suit: Dict[str, List[Card]]
    hcp_by_suit: Dict[str, int]
    total_hcp: int


# ---------------------------------------------------------------------------
# Basic deck helpers
# ---------------------------------------------------------------------------


def _weights_for_seat_profile(seat_profile: SeatProfile) -> List[float]:
    """
    Extract weight_percent for each subprofile, with safe defaults.

    If all weights are zero or missing, fall back to equal weights.
    """
    subs = list(seat_profile.subprofiles)
    if not subs:
        return []

    weights: List[float] = []
    for sub in subs:
        w = getattr(sub, "weight_percent", None)
        if w is None:
            # Default to non-zero to keep the subprofile usable
            w = 100.0
        weights.append(float(w))

    if all(w <= 0.0 for w in weights):
        # All zero -> treat as equal-weight
        weights = [1.0] * len(weights)

    return weights


def classify_viability(successes: int, attempts: int) -> str:
    """
    Classify a constraint combination's viability from empirical stats.

    This is deliberately simple and side-effect free:

        * attempts <= 0                    -> "unknown"
        * attempts < 10 and successes == 0 -> "unknown" (not enough data)
        * attempts >= 10 and successes == 0 -> "unviable"
        * 0 < success_rate < 0.1          -> "unlikely"
        * success_rate >= 0.1             -> "likely"

    This does *not* change any generator behaviour; it's intended for
    diagnostics / debug tooling (e.g. per-seat/subprofile reporting).
    """
    if attempts <= 0:
        return "unknown"

    if successes <= 0:
        # Don't call anything unviable until we've actually tried a bit.
        if attempts < 10:
            return "unknown"
        return "unviable"

    rate = successes / attempts
    if rate < 0.1:
        return "unlikely"
    return "likely"
    
    
def _choose_index_for_seat(
    rng: random.Random,
    seat_profile: SeatProfile,
) -> int:
    """
    Choose a subprofile index for a single seat.

    If there are no subprofiles or only one, always return 0.
    """
    subs = list(seat_profile.subprofiles)
    if not subs or len(subs) == 1:
        return 0

    weights = _weights_for_seat_profile(seat_profile)
    return _weighted_choice_index(rng, weights)


def _build_deck() -> List[Card]:
    ranks = "AKQJT98765432"
    suits = "SHDC"
    return [r + s for s in suits for r in ranks]


def _get_constructive_mode(profile: HandProfile) -> dict[str, bool]:
    """
    Decide which constructive-help modes are eligible for this profile.

    Currently all modes are disabled. The v1 constructive help code paths
    remain in the builder but are never activated. The feature flags that
    previously gated these modes have been removed.
    """
    return {
        "standard": False,
        "nonstandard_shadow": False,
        "nonstandard_v2": False,
    }
        
    
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
) -> set:
    """
    Identify seats with tight shape constraints that need pre-allocation help.

    For each seat, examines every suit's min_cards in the standard constraints.
    If any suit has P(>= min_cards) <= threshold, the seat is "tight".

    Args:
        chosen_subprofiles: The selected subprofile for each seat.
        threshold: Probability cutoff (default 0.19 = 19%).

    Returns:
        Set of seat names (e.g. {"N", "S"}) that need shape help.
        Empty set if no seats are tight.
    """
    tight_seats: set = set()

    for seat, sub in chosen_subprofiles.items():
        std = getattr(sub, "standard", None)
        if std is None:
            continue

        # Check each suit for tight shape constraints.
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

    return tight_seats


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

    # Random selection, then remove from deck via set lookup (O(n)).
    hand = rng.sample(deck, take)
    hand_set = set(hand)
    deck[:] = [c for c in deck if c not in hand_set]
    return hand


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

        # Find cards of this suit in the deck.
        available = [c for c in deck if len(c) >= 2 and c[1] == suit_letter]
        if not available:
            continue

        # Don't try to allocate more than available.
        actual = min(to_allocate, len(available))
        chosen = rng.sample(available, actual)
        pre_allocated.extend(chosen)

        # Remove chosen cards from deck (O(n) via set lookup).
        chosen_set = set(chosen)
        deck[:] = [c for c in deck if c not in chosen_set]

    return pre_allocated


def _deal_with_help(
    rng: random.Random,
    deck: List[Card],
    chosen_subprofiles: Dict[Seat, "SubProfile"],
    tight_seats: set,
    dealing_order: List[Seat],
) -> Dict[Seat, List[Card]]:
    """
    Deal 52 cards to 4 seats, giving shape help to tight seats.

    For each seat in dealing_order:
      - If tight: pre-allocate fraction of suit minima, fill to 13 randomly
      - If not tight (and not last): deal 13 random cards
      - Last seat: gets whatever remains (always 13 if deck started at 52)

    Mutates deck (empties it).

    Args:
        rng: Random number generator.
        deck: 52-card deck (mutable, will be emptied).
        chosen_subprofiles: Selected subprofile per seat.
        tight_seats: Set of seats needing shape help.
        dealing_order: Order to deal seats.

    Returns:
        Dict mapping each seat to its 13-card hand.
    """
    hands: Dict[Seat, List[Card]] = {}

    for i, seat in enumerate(dealing_order):
        is_last = (i == len(dealing_order) - 1)

        if is_last:
            # Last seat gets whatever remains in the deck.
            hands[seat] = list(deck)
            deck.clear()
        elif seat in tight_seats:
            # Tight seat: pre-allocate suit minima, then fill to 13.
            sub = chosen_subprofiles.get(seat)
            if sub is not None:
                pre = _pre_allocate(rng, deck, sub)
                remaining_needed = 13 - len(pre)
                fill = _random_deal(rng, deck, remaining_needed)
                hands[seat] = pre + fill
            else:
                hands[seat] = _random_deal(rng, deck, 13)
        else:
            # Non-tight seat: deal 13 random cards.
            hands[seat] = _random_deal(rng, deck, 13)

    return hands


# ---------------------------------------------------------------------------
# Subprofile selection (extracted from _build_single_constrained_deal closure
# so v2 can reuse it without duplication).
# ---------------------------------------------------------------------------

def _select_subprofiles_for_board(
    rng: random.Random,
    profile: HandProfile,
    dealing_order: List[Seat],
) -> Tuple[Dict[Seat, SubProfile], Dict[Seat, int]]:
    """
    Select a concrete subprofile index for each seat.

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
    """
    chosen_subprofiles: Dict[Seat, SubProfile] = {}
    chosen_indices: Dict[Seat, int] = {}

    # --- NS coupling logic -------------------------------------------------
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

    # --- EW coupling logic -------------------------------------------------
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

    # --- Remaining seats (including unconstrained or single-subprofile) ---
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
    # P1.4: Per-subprofile tracking for smarter nudging decisions.
    # Shape: {seat: {subprofile_idx: {"seen": int, "failed": int}}}
    seat_subprofile_stats: Dict[Seat, Dict[int, Dict[str, int]]] = {}

    while board_attempts < MAX_BOARD_ATTEMPTS:
        board_attempts += 1

        # Non-standard constructive help v2 (Piece 0/1 seam).
        # We invoke the v2 policy *after* matching a full attempt so it can
        # observe attempt-local stats (RS buckets, viability summary, etc.).
        # For now, the returned policy hints are ignored and must not affect
        # deal-generation behaviour.
        v2_policy: Dict[str, object] = {}

        # Decide which seat, if any, looks "hardest" for this board.
        # We use the v1 constructive algorithm for standard seats, but allow v2-on-std
        # to trigger the same mechanism for review.
        allow_std_constructive = constructive_mode["standard"] or constructive_mode.get("nonstandard_v2", False)

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

        # RS-specific per-attempt stats used only by the non-standard
        # constructive shadow probe.
        #
        # Shape:
        #   {
        #       seat: {
        #           "total_seen_attempts": int,
        #           "total_matched_attempts": int,
        #           "buckets": {
        #               "<bucket_key>": {
        #                   "seen_attempts": int,
        #                   "matched_attempts": int,
        #               },
        #               ...
        #           },
        #       },
        #       ...
        #   }
        rs_bucket_snapshot: Dict[
            Seat,
            Dict[str, object],
        ] = {}
        
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

            # P1.4: Track at subprofile granularity
            if idx0 is not None:
                if seat not in seat_subprofile_stats:
                    seat_subprofile_stats[seat] = {}
                if idx0 not in seat_subprofile_stats[seat]:
                    seat_subprofile_stats[seat][idx0] = {"seen": 0, "failed": 0}
                seat_subprofile_stats[seat][idx0]["seen"] += 1

            # Defensive: if we didn't pick a subprofile, treat as seat-level failure.
            if chosen_sub is None or idx0 is None:
                matched = False
                chosen_rs = None
                fail_reason = "other"  # No subprofile to classify against
            else:
                # Is this seat using Random Suit on this attempt?     
                is_rs_seat = getattr(chosen_sub, "random_suit_constraint", None) is not None

                rs_entry = None
                if is_rs_seat:
                    rs_entry = rs_bucket_snapshot.setdefault(
                        seat,
                        {"total_seen_attempts": 0, "total_matched_attempts": 0, "buckets": {}},
                    )
                    rs_entry["total_seen_attempts"] += 1

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

                # RS bucket accounting
                if is_rs_seat and rs_entry is not None and chosen_rs is not None:
                    if isinstance(chosen_rs, (list, tuple)):
                        bucket_key = ",".join(str(x) for x in chosen_rs)
                    else:
                        bucket_key = str(chosen_rs)

                    buckets = rs_entry["buckets"]
                    bucket_entry = buckets.setdefault(bucket_key, {"seen_attempts": 0, "matched_attempts": 0})
                    bucket_entry["seen_attempts"] += 1
                    if matched:
                        bucket_entry["matched_attempts"] += 1

                # PC nudge (v2 only)
                if (
                    constructive_mode.get("nonstandard_v2", False)
                    and not matched
                    and getattr(chosen_sub, "partner_contingent_constraint", None) is not None
                    and len(seat_profile.subprofiles) > 1
                ):
                    for alt_i0, alt_sub in enumerate(seat_profile.subprofiles):
                        if alt_i0 == idx0:
                            continue
                        if getattr(alt_sub, "partner_contingent_constraint", None) is None:
                            continue

                        alt_matched, alt_chosen_rs, _ = _match_seat(
                            profile=profile,
                            seat=seat,
                            hand=hands[seat],
                            seat_profile=seat_profile,
                            chosen_subprofile=alt_sub,
                            chosen_subprofile_index_1based=alt_i0 + 1,
                            random_suit_choices=random_suit_choices,
                            rng=rng,
                        )
                        if alt_matched:
                            matched, chosen_rs = alt_matched, alt_chosen_rs
                            chosen_sub = alt_sub
                            idx0 = alt_i0
                            chosen_subprofiles[seat] = alt_sub
                            chosen_indices[seat] = alt_i0
                            break

                # OC nudge (v2 only)
                if (
                    constructive_mode.get("nonstandard_v2", False)
                    and not matched
                    and getattr(chosen_sub, "opponents_contingent_suit_constraint", None) is not None
                    and len(seat_profile.subprofiles) > 1
                ):
                    for alt_i0, alt_sub in enumerate(seat_profile.subprofiles):
                        if alt_i0 == idx0:
                            continue
                        if getattr(alt_sub, "opponents_contingent_suit_constraint", None) is None:
                            continue

                        alt_matched, alt_chosen_rs, _ = _match_seat(
                            profile=profile,
                            seat=seat,
                            hand=hands[seat],
                            seat_profile=seat_profile,
                            chosen_subprofile=alt_sub,
                            chosen_subprofile_index_1based=alt_i0 + 1,
                            random_suit_choices=random_suit_choices,
                            rng=rng,
                        )
                        if alt_matched:
                            matched, chosen_rs = alt_matched, alt_chosen_rs
                            chosen_sub = alt_sub
                            idx0 = alt_i0
                            chosen_subprofiles[seat] = alt_sub
                            chosen_indices[seat] = alt_i0
                            break

                if is_rs_seat and rs_entry is not None and matched:
                    rs_entry["total_matched_attempts"] += 1

            # ---- Final seat-level failure decision for this seat ----
            if not matched:
                all_matched = False
                seat_fail_counts[seat] = seat_fail_counts.get(seat, 0) + 1

                # P1.4: Track failure at subprofile granularity
                if idx0 is not None and seat in seat_subprofile_stats:
                    if idx0 in seat_subprofile_stats[seat]:
                        seat_subprofile_stats[seat][idx0]["failed"] += 1

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
                                        
        # After matching all seats for this attempt, optionally run the
        # v2 policy seam and/or the non-standard shadow probe with up-to-date
        # viability stats.
        if constructive_mode["nonstandard_v2"] or constructive_mode["nonstandard_shadow"]:
            viability_summary_after = _summarize_profile_viability(
                seat_fail_counts,
                seat_seen_counts,
            )

            if constructive_mode["nonstandard_v2"]:
                # Piece 1: pass the same rich attempt-local stats that the
                # shadow probe sees. For now, the returned policy hints are
                # intentionally ignored.
                # P1.2: Also pass per-seat constraint flags (RS/PC/OC).
                # P1.4: Also pass per-subprofile tracking stats.
                constraint_flags = _build_constraint_flags_per_seat(chosen_subprofiles)
                v2_policy = _nonstandard_constructive_v2_policy(
                    profile=profile,
                    board_number=board_number,
                    attempt_number=board_attempts,
                    chosen_indices=chosen_indices,
                    seat_fail_counts=seat_fail_counts,
                    seat_seen_counts=seat_seen_counts,
                    viability_summary=viability_summary_after,
                    rs_bucket_snapshot=rs_bucket_snapshot,
                    constraint_flags=constraint_flags,
                    subprofile_stats=seat_subprofile_stats,
                )

            if constructive_mode["nonstandard_shadow"]:
                _shadow_probe_nonstandard_constructive(
                    profile=profile,
                    board_number=board_number,
                    attempt_number=board_attempts,
                    chosen_indices=chosen_indices,
                    seat_fail_counts=seat_fail_counts,
                    seat_seen_counts=seat_seen_counts,
                    viability_summary=viability_summary_after,
                    rs_bucket_snapshot=rs_bucket_snapshot,
                )

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

    # Identify tight seats that need shape help.
    tight_seats = _dispersion_check(chosen_subprofiles)

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

        # Build and shuffle a full deck.
        deck = _build_deck()
        rng.shuffle(deck)

        # Deal with shape help for tight seats.
        hands = _deal_with_help(
            rng, deck, chosen_subprofiles, tight_seats, dealing_order
        )

        # Match all seats against their constraints.
        all_matched = True
        random_suit_choices: Dict[Seat, List[str]] = {}
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
# Simple (fallback) generator for non-HandProfile objects
# ---------------------------------------------------------------------------

def _deal_single_board_simple(
    rng: random.Random,
    board_number: int,
    dealer: Seat,
    dealing_order: List[Seat],
) -> Deal:
    """
    Original simple random deal generator, used as a fallback when the
    profile is not a real HandProfile (e.g. tests using DummyProfile).
    """
    deck = _build_deck()
    rng.shuffle(deck)

    hands: Dict[Seat, List[Card]] = {seat: [] for seat in ("N", "E", "S", "W")}
    idx = 0
    for _ in range(13):
        for seat in dealing_order:
            hands[seat].append(deck[idx])
            idx += 1

    return Deal(
        board_number=board_number,
        dealer=dealer,
        vulnerability="None",
        hands=hands,
    )


# ---------------------------------------------------------------------------
# C2: vulnerability & rotation
# ---------------------------------------------------------------------------

def _apply_vulnerability_and_rotation(
    rng: random.Random,
    deals: List[Deal],
    rotate: bool = True,
) -> List[Deal]:
    """
    Enrich deals with vulnerability rotation and optional 2-seat rotation.

    Vulnerability:
      • Choose a random starting index from 0-3 using rng.
      • For deal i, use VULNERABILITY_SEQUENCE[(start + i) % 4].

    Rotation:
      • For each deal, with probability 0.5:
        – Swap hands N<->S, E<->W.
        – Apply same mapping to dealer.
        – Vulnerability string is unchanged.
    """
    if not deals:
        return deals

    start_idx = rng.randrange(0, len(VULNERABILITY_SEQUENCE))

    enriched: List[Deal] = []
    for i, deal in enumerate(deals):
        vul = VULNERABILITY_SEQUENCE[(start_idx + i) % len(VULNERABILITY_SEQUENCE)]

        # Start with base deal
        hands = {seat: list(cards) for seat, cards in deal.hands.items()}
        dealer = deal.dealer

        # Decide whether to rotate (only if rotate flag is True)
        if rotate and rng.random() < ROTATE_PROBABILITY:
            # Rotate hands N<->S, E<->W
            rotated_hands: Dict[Seat, List[Card]] = {}
            for seat in ("N", "E", "S", "W"):
                src = ROTATE_MAP[seat]
                rotated_hands[seat] = hands.get(src, [])
            hands = rotated_hands

            # Rotate dealer
            dealer = ROTATE_MAP.get(dealer, dealer)

        enriched.append(
            Deal(
                board_number=deal.board_number,
                dealer=dealer,
                vulnerability=vul,
                hands=hands,
            )
        )

    return enriched


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
    try:
        deals: List[Deal] = []
        for board_number in range(1, num_deals + 1):
            deal = _build_single_constrained_deal_v2(
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
    except Exception as exc:
        # Narrow scope catch-all, wrapped into domain error
        raise DealGenerationError(f"Failed to generate deals: {exc}") from exc
        
