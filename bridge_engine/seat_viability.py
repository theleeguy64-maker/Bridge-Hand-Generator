# bridge_engine/seat_viability.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Set, Tuple

from .hand_profile import (
    HandProfile,
    SeatProfile,
    SubProfile,
    StandardSuitConstraints,
    RandomSuitConstraintData,
    PartnerContingentData,
    ProfileError,
    SuitRange,
)

# Simple type aliases used throughout generation/viability.
Seat = str
Card = str

# High-card-point map (A=4, K=3, Q=2, J=1).
HCP_MAP = {"A": 4, "K": 3, "Q": 2, "J": 1}


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

def _match_standard(analysis: SuitAnalysis, std: StandardSuitConstraints) -> bool:
    # Total HCP
    if not (std.total_min_hcp <= analysis.total_hcp <= std.total_max_hcp):
        return False

    # Per-suit checks
    for suit_name, sr in [
        ("S", std.spades),
        ("H", std.hearts),
        ("D", std.diamonds),
        ("C", std.clubs),
    ]:
        count = len(analysis.cards_by_suit[suit_name])
        hcp = analysis.hcp_by_suit[suit_name]
        if not (sr.min_cards <= count <= sr.max_cards):
            return False
        if not (sr.min_hcp <= hcp <= sr.max_hcp):
            return False

    return True


def _match_random_suit(
    analysis: SuitAnalysis,
    rs: RandomSuitConstraintData,
    rng: random.Random,
) -> Optional[List[str]]:
    """
    Apply Random Suit constraint.

    Returns the list of chosen suits if matched, or None if the constraint fails.

    Notes:
      • required_suits_count distinct suits are chosen from allowed_suits.
      • When required_suits_count == 2, pair overrides are matched ignoring order.
      • Each chosen suit has its own SuitRange (from either the base suit_ranges
        or the override ranges).
    """
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

    # Random Suit (no Partner or Opponents Contingent on this seat)
    if (
        sub.random_suit_constraint is not None
        and sub.partner_contingent_constraint is None
        and sub.opponents_contingent_suit_constraint is None
    ):
        chosen = _match_random_suit(analysis, sub.random_suit_constraint, rng)
        if chosen is None:
            return False, None
        # Success: store chosen suits for this seat
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


def _subprofile_is_viable_light(sub: SubProfile, *, return_reason: bool = False):
    """
    Cheap feasibility checks that do NOT require dealing cards.
    Intended for fast 'this can never work' rejection.

    Returns:
      - bool if return_reason is False
      - (bool, str) if return_reason is True
    """
    std = sub.standard
    if std is None:
        ok, reason = False, "Missing standard constraints"
        return (ok, reason) if return_reason else ok

    # Suit-card feasibility: sum(min) <= 13 and sum(max) >= 13
    mins = (
        std.spades.min_cards
        + std.hearts.min_cards
        + std.diamonds.min_cards
        + std.clubs.min_cards
    )
    maxs = (
        std.spades.max_cards
        + std.hearts.max_cards
        + std.diamonds.max_cards
        + std.clubs.max_cards
    )
    if mins > 13:
        ok, reason = False, f"Standard mins sum to {mins} > 13"
        return (ok, reason) if return_reason else ok
    if maxs < 13:
        ok, reason = False, f"Standard maxs sum to {maxs} < 13"
        return (ok, reason) if return_reason else ok

    # HCP feasibility: a 13-card hand maxes at 37 HCP
    if getattr(std, "total_min_hcp", 0) > 37:
        ok, reason = False, f"total_min_hcp {std.total_min_hcp} > 37"
        return (ok, reason) if return_reason else ok
    if getattr(std, "total_max_hcp", 37) < 0:
        ok, reason = False, f"total_max_hcp {std.total_max_hcp} < 0"
        return (ok, reason) if return_reason else ok

    ok, reason = True, "ok"
    return (ok, reason) if return_reason else ok


def validate_profile_viability_light(profile: HandProfile) -> None:
    """
    Lightweight feasibility validation:

    Ensures each seat has at least one subprofile that is not trivially impossible
    under the cheap _subprofile_is_viable_light() checks.
    """
    for seat, sp in profile.seat_profiles.items():
        if not sp.subprofiles:
            raise ProfileError(f"Seat {seat} has no subprofiles")

        any_ok = False
        last_reason = "no subprofiles checked"
        for sub in sp.subprofiles:
            ok, reason = _subprofile_is_viable_light(sub, return_reason=True)
            if ok:
                any_ok = True
                break
            last_reason = reason

        if not any_ok:
            raise ProfileError(
                f"Seat {seat} has no viable subprofiles (light): {last_reason}"
            )
