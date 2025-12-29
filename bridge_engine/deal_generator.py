# bridge_engine/deal_generator.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence
from pathlib import Path
from datetime import datetime
import os
import random
import json

from .setup_env import SetupResult
from .hand_profile import (
    HandProfile,
    SeatProfile,
    SubProfile,
    StandardSuitConstraints,
    RandomSuitConstraintData,
    PartnerContingentData,
)

# Optional debug logging for Random Suit behaviour.
# Enable by setting env var BHG_DEBUG_RANDOM_SUIT=1 before running.
DEBUG_RANDOM_SUIT_LOG: bool = bool(os.environ.get("BHG_DEBUG_RANDOM_SUIT"))

_random_suit_debug_calls: int = 0
_random_suit_debug_successes: int = 0
_random_suit_debug_failures: int = 0

# Debug counters for where boards fail during Section C
_random_suit_board_failures_by_seat: Dict[Seat, int] = {"N": 0, "E": 0, "S": 0, "W": 0}
_random_suit_hand_failures_by_seat: Dict[Seat, int] = {"N": 0, "E": 0, "S": 0, "W": 0}

_RANDOM_SUIT_LOG_PATH: Optional[Path] = None

def set_random_suit_log_path(path: Path) -> None:
    """
    Optional helper: set a file to receive Random Suit debug logs.
    You can call this from the orchestrator before generate_deals(...).
    """
    global _RANDOM_SUIT_LOG_PATH
    _RANDOM_SUIT_LOG_PATH = path
    try:
        # Start fresh for each run
        path.write_text("", encoding="utf-8")
    except OSError:
        _RANDOM_SUIT_LOG_PATH = None

def dump_random_suit_stats() -> None:
    """
    Debug helper: write the current RandomSuit counters to JSON if
    RANDOM_SUIT_STATS_FILE is set in the environment.

    This is intended for orchestrator's debug menu and is safe to call
    even if RandomSuit was never used.
    """
    path = os.getenv("RANDOM_SUIT_STATS_FILE")
    if not path:
        # No stats file configured → silently do nothing.
        return

    data = {
        "calls": _random_suit_debug_calls,
        "successes": _random_suit_debug_successes,
        "failures": _random_suit_debug_failures,
    }

    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except OSError:
        # Never let debug logging kill a deal run.
        pass

# Environment variable names for optional Random Suit debugging output.
_RANDOM_SUIT_DEBUG_FILE_ENV = "RANDOM_SUIT_DEBUG_FILE"
_RANDOM_SUIT_STATS_FILE_ENV = "RANDOM_SUIT_STATS_FILE"

def _debug_log_random_suit(message: str) -> None:
    """
    Append a debug line and refresh the stats JSON, if the user has
    configured RANDOM_SUIT_DEBUG_FILE / RANDOM_SUIT_STATS_FILE.

    This is best-effort only: any errors are swallowed so debug logging
    can never break deal generation.
    """
    debug_path_str = os.getenv(_RANDOM_SUIT_DEBUG_FILE_ENV)
    stats_path_str = os.getenv(_RANDOM_SUIT_STATS_FILE_ENV)

    # Fast path: nothing configured, do nothing.
    if not debug_path_str and not stats_path_str:
        return

    try:
        # Text log (append)
        if debug_path_str:
            debug_path = Path(debug_path_str)
            debug_path.parent.mkdir(parents=True, exist_ok=True)
            with debug_path.open("a", encoding="utf-8") as f:
                f.write(message + "\n")

        # Stats snapshot (overwrite with latest counters)
        if stats_path_str:
            stats_path = Path(stats_path_str)
            stats_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "calls": _random_suit_debug_calls,
                "successes": _random_suit_debug_successes,
                "failures": _random_suit_debug_failures,
            }
            stats_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    except Exception:
        # Debugging only – never crash the generator because logging failed.
        pass

# ----------------------------------------------------------------------
# Global HCP sanity check
# ----------------------------------------------------------------------

def _accumulate_hcp_bounds_for_seat(sp: SeatProfile) -> tuple[Optional[int], Optional[int]]:
    """
    Return a conservative (min_hcp, max_hcp) pair for this seat across all
    subprofiles, if any explicit HCP ranges are defined.

    We *only* use these to prove impossibility, never to reject something
    that might be feasible. So:
      - total_min is the sum of per-seat minimum HCPs that are explicitly
        specified (ignoring seats with no min).
      - total_max is the sum of per-seat maximum HCPs, but we only treat
        it as a hard bound if *all* four seats have a max.
    """
    min_hcp: Optional[int] = None
    max_hcp: Optional[int] = None

    for sub in getattr(sp, "subprofiles", []) or []:
        std = getattr(sub, "standard", None)
        if std is None:
            continue

        # Adjust attribute names to your actual C1/HCP fields:
        sub_min = getattr(std, "min_hcp", None)
        sub_max = getattr(std, "max_hcp", None)

        if sub_min is not None:
            min_hcp = sub_min if min_hcp is None else min(min_hcp, sub_min)
        if sub_max is not None:
            max_hcp = sub_max if max_hcp is None else max(max_hcp, sub_max)

    return min_hcp, max_hcp


def _check_global_hcp_feasibility(profile: HandProfile) -> None:
    """
    Very conservative global HCP check.

    - If the sum of all *explicit* seat minima exceeds 40 HCP, the profile
      is impossible.
    - If *all four* seats have an explicit HCP max, and their sum is
      strictly less than 40, the profile is also impossible.

    We intentionally do NOT complain if some seats have no HCP bounds, or
    only mins, or only maxes: those might still be feasible.
    """
    total_min = 0
    total_max = 0
    num_seats_with_max = 0

    for seat in ("N", "E", "S", "W"):
        sp = profile.seat_profiles.get(seat)
        if sp is None:
            continue

        seat_min, seat_max = _accumulate_hcp_bounds_for_seat(sp)

        if seat_min is not None:
            total_min += seat_min
        # For max we also need to know if *this* seat had any explicit max at all.
        if seat_max is not None:
            total_max += seat_max
            num_seats_with_max += 1

    # No explicit HCP constraints at all → nothing to check.
    if total_min == 0 and num_seats_with_max == 0:
        return

    # 40 HCP is a hard upper bound; if the sum of known minima is already
    # above that, this profile cannot be satisfied.
    if total_min > 40:
        raise DealGenerationError(
            f"Profile '{getattr(profile, 'profile_name', '<unknown>')}' "
            f"appears impossible: combined minimum HCP {total_min} exceeds 40."
        )

    # For a hard max check we require all four seats to have an explicit max.
    if num_seats_with_max == 4 and total_max < 40:
        raise DealGenerationError(
            f"Profile '{getattr(profile, 'profile_name', '<unknown>')}' "
            f"appears impossible: combined maximum HCP {total_max} is below 40."
        )

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

Seat = str  # 'N', 'E', 'S', 'W'
Card = str  # e.g. 'AS', 'TD'

HCP_MAP: Dict[str, int] = {"A": 4, "K": 3, "Q": 2, "J": 1}

MAX_BOARD_ATTEMPTS: int = 10000
MAX_ATTEMPTS_HAND_2_3: int = 1000
ROTATE_PROBABILITY: float = 0.5

VULNERABILITY_SEQUENCE: List[str] = ["None", "NS", "EW", "Both"]

ROTATE_MAP: Dict[Seat, Seat] = {
    "N": "S",
    "S": "N",
    "E": "W",
    "W": "E",
}

# Toggleable debug flag for Section C
DEBUG_SECTION_C: bool = False


class DealGenerationError(Exception):
    """Raised when something goes wrong during deal generation."""


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

def _build_deck() -> List[Card]:
    ranks = "AKQJT98765432"
    suits = "SHDC"
    return [r + s for s in suits for r in ranks]


def _compute_suit_analysis(hand: List[Card]) -> SuitAnalysis:
    """
    Compute per-suit card lists and HCP, plus total HCP, for a 13-card hand.

    This is intentionally very cheap: it should be safe to call on every
    candidate hand during matching.
    """
    # Local dicts to avoid repeated global lookups and construction
    cards_by_suit: Dict[str, List[Card]] = {"S": [], "H": [], "D": [], "C": []}
    hcp_by_suit: Dict[str, int] = {"S": 0, "H": 0, "D": 0, "C": 0}

    hcp_map = HCP_MAP  # local alias for speed
    total_hcp = 0

    for card in hand:
        # Expect "RS" format (rank + suit). Be defensive but cheap.
        if len(card) != 2:
            continue

        rank = card[0]
        suit = card[1]

        suit_cards = cards_by_suit.get(suit)
        if suit_cards is None:
            # Unknown suit – defensive guard, but shouldn't happen.
            continue

        suit_cards.append(card)
        value = hcp_map.get(rank, 0)
        hcp_by_suit[suit] += value
        total_hcp += value

    return SuitAnalysis(
        cards_by_suit=cards_by_suit,
        hcp_by_suit=hcp_by_suit,
        total_hcp=total_hcp,
    )
        
# ---------------------------------------------------------------------------
# Standard / Random Suit / Partner Contingent matching
# ---------------------------------------------------------------------------

def _match_standard(
    analysis: "SuitAnalysis",
    std: StandardSuitConstraints,
    skip_suits: Optional[Iterable[str]] = None,
) -> bool:
    """
    Check if a hand matches the "standard" per-suit and total HCP constraints.

    If skip_suits is provided, any suit in that iterable is *not* checked at
    the suit level (length + suit HCP), but the total HCP constraint still
    applies to the whole hand.
    """
    # Total HCP check first (cheap, still applies even if some suits are
    # handled by RandomSuit constraints).
    if not (std.total_min_hcp <= analysis.total_hcp <= std.total_max_hcp):
        return False

    skip = set(skip_suits or ())

    # Suit-level checks (length + HCP) for all suits NOT in skip
    for suit_name, sr in [
        ("S", std.spades),
        ("H", std.hearts),
        ("D", std.diamonds),
        ("C", std.clubs),
    ]:
        if suit_name in skip:
            continue

        suit_cards = analysis.cards_by_suit[suit_name]
        count = len(suit_cards)
        hcp = analysis.hcp_by_suit[suit_name]

        if not (sr.min_cards <= count <= sr.max_cards):
            return False
        if not (sr.min_hcp <= hcp <= sr.max_hcp):
            return False

    return True

def _dump_random_suit_stats() -> None:
    if not RANDOM_SUIT_STATS_FILE:
        return

    payload = {
        "calls": _random_suit_debug_calls,
        "successes": _random_suit_debug_successes,
        "failures": _random_suit_debug_failures,
        "board_failures_by_seat": _random_suit_board_failures_by_seat,
        "hand_failures_by_seat": _random_suit_hand_failures_by_seat,
    }
    try:
        Path(RANDOM_SUIT_STATS_FILE).write_text(
            json.dumps(payload, indent=2),
            encoding="utf-8",
        )
    except OSError:
        # Don't let debug kill the run
        pass
        
def _match_random_suit(
    analysis: SuitAnalysis,
    rs: RandomSuitConstraintData,
    rng: random.Random,
) -> Optional[List[str]]:
    """
    Decide whether this hand can satisfy the Random Suit constraint rs.

    Returns:
      • None           → this hand cannot satisfy rs
      • ['S'], ['H'], ['D'], ['C'], or multi-suit list → chosen suit(s)
    """

    # Debug counters (used for optional logging)
    global _random_suit_debug_calls, _random_suit_debug_successes, _random_suit_debug_failures
    _random_suit_debug_calls += 1

    def _core_match() -> Optional[List[str]]:
        """
        Core matching logic with no side-effects on debug counters.
        """
        # Apply Random Suit constraint.

        # Notes:
        #   • required_suits_count distinct suits are chosen from allowed_suits.
        #   • When required_suits_count == 2, pair overrides are matched ignoring order.
        #   • Each chosen suit has its own SuitRange (from either the base suit_ranges
        #     or the override ranges).
        allowed = list(rs.allowed_suits)
        if not allowed or rs.required_suits_count <= 0:
            return None
        if rs.required_suits_count > len(allowed):
            return None

        # Choose distinct suits
        chosen_suits = rng.sample(allowed, rs.required_suits_count)

        # Decide which SuitRange applies for each chosen suit
        # Default mapping: index -> suit_ranges[index]
        ranges_by_suit: Dict[str, object] = {}

        if rs.required_suits_count == 2 and rs.pair_overrides:
            # Check overrides ignoring order
            sorted_pair = tuple(sorted(chosen_suits))  # type: ignore[assignment]
            matched_override = None
            for po in rs.pair_overrides:
                if tuple(sorted(po.suits)) == sorted_pair:
                    matched_override = po
                    break

            if matched_override is not None:
                # Map by suit name, order not meaningful
                ranges_by_suit[matched_override.suits[0]] = matched_override.first_range
                ranges_by_suit[matched_override.suits[1]] = matched_override.second_range
            else:
                # Fall back to base suit_ranges
                for idx, suit in enumerate(chosen_suits):
                    if idx >= len(rs.suit_ranges):
                        return None
                    ranges_by_suit[suit] = rs.suit_ranges[idx]
        else:
            # No pair override scenario
            for idx, suit in enumerate(chosen_suits):
                if idx >= len(rs.suit_ranges):
                    return None
                ranges_by_suit[suit] = rs.suit_ranges[idx]

        # Now check each chosen suit against its SuitRange
        for suit in chosen_suits:
            sr = ranges_by_suit[suit]
            count = len(analysis.cards_by_suit[suit])
            hcp = analysis.hcp_by_suit[suit]
            if not (sr.min_cards <= count <= sr.max_cards):  # type: ignore[attr-defined]
                return None
            if not (sr.min_hcp <= hcp <= sr.max_hcp):        # type: ignore[attr-defined]
                return None

        return chosen_suits

    # ---- debug-aware wrapper ----
    result = _core_match()
    if result is None:
        _random_suit_debug_failures += 1
    else:
        _random_suit_debug_successes += 1
    return result
    
def _match_partner_contingent(
    analysis: SuitAnalysis,
    pc: PartnerContingentData,
    partner_suits: List[str],
) -> bool:
    """
    Apply Partner Contingent-Suit constraint.

    Rule:
      • Partner has Random Suit constraint and has chosen N suits.
      • The partner's Contingent Suit is defined as the first chosen suit.
      • This hand must satisfy suit_range in that single suit.
    """
    if not partner_suits:
        return False

    sr = pc.suit_range
    suit = partner_suits[0]
    if suit not in analysis.cards_by_suit:
        return False

    count = len(analysis.cards_by_suit[suit])
    hcp = analysis.hcp_by_suit[suit]
    return sr.min_cards <= count <= sr.max_cards and sr.min_hcp <= hcp <= sr.max_hcp

def _match_subprofile(
    analysis: SuitAnalysis,
    seat: Seat,
    sub: SubProfile,
    random_suit_choices: Dict[Seat, List[str]],
    rng: random.Random,
) -> (bool, Optional[List[str]]):
    """
    Attempt to match a single SubProfile to this 13-card hand.

    Returns:
      (matched, chosen_random_suits_for_this_seat_or_None)
    """
    # Always check Standard first
    if not _match_standard(analysis, sub.standard):
        return False, None

    # Random Suit only (no Partner or Opponents)
    #
    # New behaviour:
    #   - RandomSuitConstraintData chooses one or more suits for this *deal*.
    #   - For those chosen suits, we rely on the RandomSuit ranges (length + HCP).
    #   - For all *other* suits, we still enforce the standard suit constraints.
    #   - Total HCP (std.total_min_hcp/max_hcp) still applies to the whole hand.
    if (
        sub.random_suit_constraint is not None
        and sub.partner_contingent_constraint is None
        and sub.opponents_contingent_suit_constraint is None
    ):
        # First, let RandomSuit pick the applicable suit(s) for this hand.
        chosen = _match_random_suit(analysis, sub.random_suit_constraint, rng)
        if chosen is None:
            return False, None

        # Then, run the standard checks *excluding* those chosen suits,
        # so their length/HCP is controlled only by the RandomSuit constraint.
        if not _match_standard(analysis, sub.standard, skip_suits=chosen):
            return False, None

        # Success: we matched both RandomSuit and standard for non-random suits.
        return True, chosen

    # Partner Contingent-Suit (no Random Suit or Opponents on this seat)
    if (
        sub.partner_contingent_constraint is not None
        and sub.random_suit_constraint is None
        and sub.opponents_contingent_suit_constraint is None
    ):
        pc = sub.partner_contingent_constraint
        partner = pc.partner_seat
        partner_suits = random_suit_choices.get(partner)
        if not partner_suits:
            # If partner hasn't chosen Random Suit suits yet, this cannot match
            return False, None

        if _match_partner_contingent(analysis, pc, partner_suits):
            return True, None
        return False, None

    # Opponents Contingent-Suit (no Random Suit or Partner on this seat)
    if (
        sub.opponents_contingent_suit_constraint is not None
        and sub.random_suit_constraint is None
        and sub.partner_contingent_constraint is None
    ):
        oc = sub.opponents_contingent_suit_constraint
        opponent = oc.opponent_seat
        opp_suits = random_suit_choices.get(opponent)
        if not opp_suits:
            # If opponent hasn't chosen Random Suit suits yet, this cannot match
            return False, None

        # Opponent's Contingent Suit = first chosen suit
        suit = opp_suits[0]
        sr = oc.suit_range
        if suit not in analysis.cards_by_suit:
            return False, None

        count = len(analysis.cards_by_suit[suit])
        hcp = analysis.hcp_by_suit[suit]
        if sr.min_cards <= count <= sr.max_cards and sr.min_hcp <= hcp <= sr.max_hcp:
            return True, None
        return False, None

    # Standard-only sub-profile
    # (no random_suit_constraint, no partner_contingent_constraint, no opponents_contingent_suit_constraint)
    if (
        sub.random_suit_constraint is None
        and sub.partner_contingent_constraint is None
        and sub.opponents_contingent_suit_constraint is None
    ):
        return True, None

    # Any other combination is invalid by design; treat as not matching.
    return False, None

def _is_excluded_for_seat_subprofile(
    profile: HandProfile,
    seat: Seat,
    subprofile_index_1based: Optional[int],
    analysis: SuitAnalysis,
) -> bool:
    if subprofile_index_1based is None:
        return False

    # Compute canonical shape string in S/H/D/C order
    lengths = {
        "S": len(analysis.cards_by_suit.get("S", [])),
        "H": len(analysis.cards_by_suit.get("H", [])),
        "D": len(analysis.cards_by_suit.get("D", [])),
        "C": len(analysis.cards_by_suit.get("C", [])),
    }
    shape = f"{lengths['S']}{lengths['H']}{lengths['D']}{lengths['C']}"

    for exc in getattr(profile, "subprofile_exclusions", []):
        if getattr(exc, "seat", None) != seat:
            continue
        if getattr(exc, "subprofile_index", None) != subprofile_index_1based:
            continue

        excluded_shapes = getattr(exc, "excluded_shapes", None)
        if excluded_shapes:
            if shape in excluded_shapes:
                return True

        clauses = getattr(exc, "clauses", None)
        if clauses:
            ok = True
            for c in clauses:
                group = getattr(c, "group", None)
                length_eq = int(getattr(c, "length_eq", -1))
                want_count = int(getattr(c, "count", -1))

                if group == "MAJOR":
                    suits = ("S", "H")
                elif group == "MINOR":
                    suits = ("D", "C")
                elif group == "ANY":
                    suits = ("S", "H", "D", "C")
                else:
                    ok = False
                    break

                got = sum(1 for s in suits if lengths[s] == length_eq)
                if got != want_count:
                    ok = False
                    break

            if ok:
                return True

    return False

def _seat_has_c1_constraints(
    seat_profile: Optional[SeatProfile],
    chosen_subprofile: Optional[SubProfile],
) -> bool:
    """
    Return True if this seat should go through the normal C1 / RandomSuit /
    partner-contingent logic.

    For now we are deliberately conservative: *any* seat that has a
    SeatProfile is treated as constrained. That guarantees we don't
    accidentally skip RandomSuit or other non-standard constraints.

    We still keep this helper as a hook so we can later relax it for
    truly unconstrained seats once we've catalogued all the constraint
    fields.
    """
    # No SeatProfile -> truly unconstrained; caller already fast-paths this.
    if seat_profile is None:
        return False

    # Any seat with a SeatProfile is considered constrained.
    return True
    
def _match_seat(
    profile: HandProfile,
    seat: Seat,
    hand: List[Card],
    seat_profile: Optional[SeatProfile],
    chosen_subprofile: Optional[SubProfile],
    chosen_subprofile_index_1based: Optional[int],
    random_suit_choices: Dict[Seat, List[str]],
    rng: random.Random,
) -> (bool, Optional[List[str]]):
    """
    Match a 13-card hand against the chosen SubProfile for a given seat.

    Logic:
      • If seat is unconstrained (no SeatProfile), accept any hand.
      • Otherwise, use the pre-selected SubProfile for this seat for the entire deal.
        We do NOT randomly switch subprofiles per attempt; uniform 1/N selection
        across deals is handled by the caller.

    Returns:
      (matched, chosen_random_suits_for_this_seat_or_None)
    """
    # Unconstrained seat: any 13 cards are acceptable.
    if seat_profile is None:
        return True, None

    # Fast-path: if this seat has no *effective* C1 constraints for the
    # chosen subprofile (i.e. it's effectively unconstrained), accept
    # immediately and skip all HCP/suit analysis.
    #
    # This is deliberately conservative: _seat_has_c1_constraints() will
    # only return False for "trivially unconstrained" cases, so it won't
    # change behaviour for any of the real test profiles.
    if not _seat_has_c1_constraints(seat_profile, chosen_subprofile):
        return True, None

    # If no chosen subprofile was provided, fall back defensively to first one
    if chosen_subprofile is None:
        if not seat_profile.subprofiles:
            return True, None
        subprofiles: List[SubProfile] = [seat_profile.subprofiles[0]]
    else:
        subprofiles = [chosen_subprofile]

    analysis = _compute_suit_analysis(hand)

    for sub in subprofiles:
        matched, chosen = _match_subprofile(
            analysis=analysis,
            seat=seat,
            sub=sub,
            random_suit_choices=random_suit_choices,
            rng=rng,
        )
        if matched:
            if _is_excluded_for_seat_subprofile(
                profile=profile,
                seat=seat,
                subprofile_index_1based=chosen_subprofile_index_1based,
                analysis=analysis,
            ):
                return False, None
            return True, chosen

    return False, None


# -------------------------------------    dealing_order:--------------------------------------
# Constrained board construction (C1)
# ---------------------------------------------------------------------------

def _build_single_constrained_deal(
    rng: random.Random,
    profile: HandProfile,
    board_number: int,
) -> Deal:
    """
    Attempt to build a single constrained deal for the given board number.

    Rules:
      • At the start of this deal, for each constrained seat we randomly select
        exactly one SubProfile from that SeatProfile.
      • That chosen SubProfile is fixed for a *single board attempt*.
        If the board has to be restarted, we are allowed to pick a new
        sub-profile combination so we don't tunnel forever on a bad combo.
      • Hand 1: keep trying candidate hands from the full deck.
      • Hand 2 & 3: up to MAX_ATTEMPTS_HAND_2_3 candidate hands each.
      • Hand 4: remaining 13 cards; if they fail constraints, restart board.
      • Overall limited by MAX_BOARD_ATTEMPTS.
    """
    # Reset Random Suit debug counters for this board (across all attempts)
    global _random_suit_debug_calls, _random_suit_debug_successes, _random_suit_debug_failures
    _random_suit_debug_calls = 0
    _random_suit_debug_successes = 0
    _random_suit_debug_failures = 0

    dealing_order: List[Seat] = list(profile.hand_dealing_order)

    # ------------------------------------------------------------------
    # NS driver/follower semantics + sub-profile index matching
    # ------------------------------------------------------------------
    mode = (getattr(profile, "ns_role_mode", "north_drives") or "north_drives").lower()

    # Initial debug snapshot so long-running boards always create a log file.
    _debug_log_random_suit(
        f"Board {board_number}: START; "
        f"profile={getattr(profile, 'profile_name', '<unknown>')!r}, "
        f"dealer={profile.dealer}, "
        f"ns_role_mode={mode}, "
        f"hand_dealing_order={''.join(dealing_order)}"
    )

    ns_role_by_seat: Dict[Seat, str] = {}

    if mode != "no_driver_no_index":
        # Normal driver/follower behaviour for all modes *except*
        # "no_driver_no_index".
        ns_driver: Seat
        try:
            # Newer HandProfile.ns_driver_seat signatures may accept rng.
            ns_driver = profile.ns_driver_seat(rng)  # type: ignore[arg-type]
        except TypeError:
            # Older helper without rng parameter.
            ns_driver = profile.ns_driver_seat()  # type: ignore[call-arg]
        except AttributeError:
            # Very old profiles: default to North driving.
            ns_driver = "N"

        if ns_driver not in ("N", "S"):
            ns_driver = "N"

        ns_follower: Seat = "S" if ns_driver == "N" else "N"

        ns_role_by_seat = {
            ns_driver: "driver",
            ns_follower: "follower",
        }

    # NOTE:
    # - For mode == "no_driver_no_index", ns_role_by_seat stays empty.
    #   Later selection code that looks up ns_role_by_seat.get(seat)
    #   will see None for both N and S and should fall back to the
    #   generic "independent weighted subprofile selection" path.

    def _select_subprofiles_for_board() -> Tuple[Dict[Seat, Optional[SubProfile]], Dict[Seat, Optional[int]]]:
        """
        Choose one SubProfile per seat for *this board attempt*,
        applying NS/EW coupling and ns_role_usage filtering.
        """
        chosen_subprofiles: Dict[Seat, Optional[SubProfile]] = {}
        chosen_subprofile_indices: Dict[Seat, Optional[int]] = {}

        for seat in ("N", "E", "S", "W"):
            sp = profile.seat_profiles.get(seat)
            if sp is None or not sp.subprofiles:
                chosen_subprofiles[seat] = None
                chosen_subprofile_indices[seat] = None
                continue

            all_subs = list(sp.subprofiles)

            # Seat-specific eligibility filter for NS based on driver/follower.
            if seat in ("N", "S"):
                seat_role = ns_role_by_seat.get(seat)
                if seat_role == "driver":
                    eligible_indices = [
                        i
                        for i, sub in enumerate(all_subs)
                        if getattr(sub, "ns_role_usage", "any") in ("any", "driver_only")
                    ]
                elif seat_role == "follower":
                    eligible_indices = [
                        i
                        for i, sub in enumerate(all_subs)
                        if getattr(sub, "ns_role_usage", "any") in ("any", "follower_only")
                    ]
                else:
                    # No driver/follower semantics: don't filter NS subprofiles.
                    eligible_indices = list(range(len(all_subs)))
            else:
                # EW unaffected by ns_role_usage.
                eligible_indices = list(range(len(all_subs)))

            # Extra defensive fallback: if validation has somehow allowed a
            # configuration with no eligible subprofiles, revert to "any".
            if not eligible_indices:
                eligible_indices = list(range(len(all_subs)))

            # Weighted subprofile choice using weight_percent,
            # restricted to the eligible indices for this seat.
            weights = [float(all_subs[i].weight_percent) for i in eligible_indices]

            # If the total weight is zero (e.g. profile never validated),
            # fall back to uniform choice so legacy/hand-written profiles
            # still work.
            if not weights or sum(weights) <= 0.0:
                idx = eligible_indices[rng.randrange(len(eligible_indices))]
            else:
                rel_idx = _weighted_choice_index(rng, weights)
                idx = eligible_indices[rel_idx]

            chosen_subprofiles[seat] = all_subs[idx]
            chosen_subprofile_indices[seat] = idx

        # ------------------------------------------------------------------
        # NS + EW sub-profile index coupling (F3 semantics)
        # ------------------------------------------------------------------

        def _apply_pair_coupling(opener: Seat, responder: Seat) -> None:
            opener_sp = profile.seat_profiles.get(opener)
            resp_sp = profile.seat_profiles.get(responder)
            if opener_sp is None or resp_sp is None:
                return
            if not opener_sp.subprofiles or not resp_sp.subprofiles:
                return

            # Only couple when both sides have >1 and counts match (unambiguous).
            if len(opener_sp.subprofiles) <= 1 and len(resp_sp.subprofiles) <= 1:
                return
            if len(opener_sp.subprofiles) != len(resp_sp.subprofiles):
                return

            opener_idx = chosen_subprofile_indices.get(opener)
            if opener_idx is None:
                return

            if 0 <= opener_idx < len(resp_sp.subprofiles):
                chosen_subprofiles[responder] = resp_sp.subprofiles[opener_idx]
                chosen_subprofile_indices[responder] = opener_idx

        # Partnerships: NS and EW
        # For NS, ask the HandProfile which seat "drives" the partnership.
        try:
            ns_driver = profile.ns_driver_seat(rng)
        except TypeError:
            # Backwards compat: helper without rng parameter.
            ns_driver = profile.ns_driver_seat()  # type: ignore[call-arg]
        except AttributeError:
            # Very old HandProfile instances without the helper:
            # original “N drives, S responds” semantics.
            ns_driver = "N"

        if ns_driver not in ("N", "S"):
            ns_driver = "N"

        ns_responder: Seat = "S" if ns_driver == "N" else "N"
        _apply_pair_coupling(ns_driver, ns_responder)

        # EW: keep legacy behaviour – East is opener, West is responder.
        _apply_pair_coupling("E", "W")

        return chosen_subprofiles, chosen_subprofile_indices

    board_attempts = 0

    while board_attempts < MAX_BOARD_ATTEMPTS:
        board_attempts += 1

        # New: pick a *fresh* sub-profile combination for this board attempt.
        chosen_subprofiles, chosen_subprofile_indices = _select_subprofiles_for_board()

        # Periodic debug snapshot every 100 board attempts
        if board_attempts % 100 == 0:
            _debug_log_random_suit(
                f"Board {board_number}: still searching; "
                f"board_attempts={board_attempts}, "
                f"RandomSuit calls={_random_suit_debug_calls}, "
                f"successes={_random_suit_debug_successes}, "
                f"failures={_random_suit_debug_failures}"
            )

        deck = _build_deck()
        rng.shuffle(deck)
        remaining = list(deck)
        hands: Dict[Seat, List[Card]] = {}
        random_suit_choices: Dict[Seat, List[str]] = {}

        success_for_board = True

        for idx, seat in enumerate(dealing_order):
            seat_profile = profile.seat_profiles.get(seat)
            sub_for_seat = chosen_subprofiles.get(seat)

            if idx < 3:
                # Seats 0,1,2: draw from remaining with a bounded inner loop.
                max_attempts = (
                    MAX_BOARD_ATTEMPTS  # effectively unbounded for seat 0
                    if idx == 0
                    else MAX_ATTEMPTS_HAND_2_3
                )
                attempts = 0
                matched_seat = False
                chosen_random_suits_for_seat: Optional[List[str]] = None
                chosen_hand: Optional[List[Card]] = None

                while attempts < max_attempts:
                    attempts += 1
                    if len(remaining) < 13:
                        matched_seat = False
                        break

                    candidate = rng.sample(remaining, 13)
                    matched, chosen = _match_seat(
                        profile=profile,
                        seat=seat,
                        hand=candidate,
                        seat_profile=seat_profile,
                        chosen_subprofile=sub_for_seat,
                        chosen_subprofile_index_1based=(
                            (chosen_subprofile_indices.get(seat) + 1)
                            if chosen_subprofile_indices.get(seat) is not None
                            else None
                        ),
                        random_suit_choices=random_suit_choices,
                        rng=rng,
                    )
                    if matched:
                        matched_seat = True
                        chosen_random_suits_for_seat = chosen
                        chosen_hand = candidate
                        break

                if not matched_seat or chosen_hand is None:
                    # Track which seat is failing to find hands
                    _random_suit_board_failures_by_seat[seat] += 1
                    _random_suit_hand_failures_by_seat[seat] += attempts

                    # Optional throttled log (to avoid spam)
                    if board_attempts <= 20 or board_attempts % 500 == 0:
                        _debug_log_random_suit(
                            f"Board {board_number}: seat {seat} FAILED after "
                            f"{attempts} candidate hands; "
                            f"board_attempts={board_attempts}, "
                            f"RandomSuit calls={_random_suit_debug_calls}, "
                            f"successes={_random_suit_debug_successes}, "
                            f"failures={_random_suit_debug_failures}"
                        )

                    success_for_board = False
                    break

                # Commit chosen hand
                hands[seat] = chosen_hand
                for card in chosen_hand:
                    remaining.remove(card)

                if chosen_random_suits_for_seat is not None:
                    random_suit_choices[seat] = chosen_random_suits_for_seat

            else:
                # Final seat: must take the remaining 13 cards in one shot.
                if len(remaining) != 13:
                    success_for_board = False
                    break

                candidate = list(remaining)
                matched, chosen = _match_seat(
                    profile=profile,
                    seat=seat,
                    hand=candidate,
                    seat_profile=seat_profile,
                    chosen_subprofile=sub_for_seat,
                    chosen_subprofile_index_1based=(
                        (chosen_subprofile_indices.get(seat) + 1)
                        if chosen_subprofile_indices.get(seat) is not None
                        else None
                    ),
                    random_suit_choices=random_suit_choices,
                    rng=rng,
                )
                if not matched:
                    _random_suit_board_failures_by_seat[seat] += 1
                    _random_suit_hand_failures_by_seat[seat] += 1

                    if board_attempts <= 20 or board_attempts % 500 == 0:
                        _debug_log_random_suit(
                            f"Board {board_number}: seat {seat} FAILED on final-13 "
                            f"candidate; board_attempts={board_attempts}, "
                            f"RandomSuit calls={_random_suit_debug_calls}, "
                            f"successes={_random_suit_debug_successes}, "
                            f"failures={_random_suit_debug_failures}"
                        )

                    success_for_board = False
                    break

                hands[seat] = candidate
                if chosen is not None:
                    random_suit_choices[seat] = chosen
                remaining.clear()

        if success_for_board and len(hands) == 4:
            _debug_log_random_suit(
                f"Board {board_number}: SUCCESS after {board_attempts} board attempts; "
                f"RandomSuit calls={_random_suit_debug_calls}, "
                f"successes={_random_suit_debug_successes}, "
                f"failures={_random_suit_debug_failures}"
            )
            return Deal(
                board_number=board_number,
                dealer=profile.dealer,
                vulnerability="None",  # set later in _apply_vulnerability_and_rotation
                hands=hands,
            )

    # If we fall out of the loop entirely, we failed this board.
    _debug_log_random_suit(
        f"Board {board_number}: FAILED after {board_attempts} board attempts; "
        f"RandomSuit calls={_random_suit_debug_calls}, "
        f"successes={_random_suit_debug_successes}, "
        f"failures={_random_suit_debug_failures}"
    )
    raise DealGenerationError(
        f"Unable to generate constrained deal for board {board_number} "
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

    rng = random.Random(setup.seed)

    # Fallback path for tests / dummy profiles
    if not isinstance(profile, HandProfile):
        dealer: Seat = getattr(profile, "dealer", "N")
        dealing_order_attr = getattr(profile, "hand_dealing_order", ["N", "E", "S", "W"])
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

    # Full constrained path
    # Before we start the expensive search, do a quick global HCP sanity check.
    _check_global_hcp_feasibility(profile)

    try:
        deals: List[Deal] = []
        for board_number in range(1, num_deals + 1):
            deal = _build_single_constrained_deal(
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