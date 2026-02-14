# bridge_engine/seat_viability.py
from __future__ import annotations

import random
from typing import Dict, List, Optional, Tuple, Union

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
from .deal_generator_types import SuitAnalysis, _CARD_HCP


# Simple type aliases used throughout generation/viability.
Seat = str
Card = str

# HCP lookup: use pre-built _CARD_HCP dict from deal_generator_types
# (maps full card string e.g. "AS" → 4, "2H" → 0).


# ---------------------------------------------------------------------------
# Basic deck helpers
# ---------------------------------------------------------------------------


def _compute_suit_analysis(hand: List[Card]) -> SuitAnalysis:
    """
    Compute per-suit card lists and HCP, plus total HCP, for a 13-card hand.

    This is intentionally very cheap: it should be safe to call on every
    candidate hand during matching.
    """
    # Local dicts to avoid repeated global lookups and construction
    cards_by_suit: Dict[str, List[Card]] = {"S": [], "H": [], "D": [], "C": []}
    hcp_by_suit: Dict[str, int] = {"S": 0, "H": 0, "D": 0, "C": 0}

    card_hcp = _CARD_HCP  # local alias for speed
    total_hcp = 0

    for card in hand:
        # Expect "RS" format (rank + suit). Be defensive but cheap.
        if len(card) != 2:
            continue

        suit = card[1]

        suit_cards = cards_by_suit.get(suit)
        if suit_cards is None:
            # Unknown suit – defensive guard, but shouldn't happen.
            continue

        suit_cards.append(card)
        value = card_hcp.get(card, 0)
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
    analysis: SuitAnalysis, std: StandardSuitConstraints
) -> Tuple[bool, Optional[str]]:
    """
    Match a hand's SuitAnalysis against StandardSuitConstraints.

    Returns:
        (matched: bool, fail_reason: Optional[str])
        - If matched is True, fail_reason is None
        - If matched is False, fail_reason is one of:
          - "hcp": Failed total HCP or per-suit HCP check
          - "shape": Failed per-suit card count check
    """
    # Total HCP check (HCP type failure)
    if not (std.total_min_hcp <= analysis.total_hcp <= std.total_max_hcp):
        return False, "hcp"

    # Per-suit checks — unrolled to avoid constructing a temporary list
    # of tuples on every call (this function is hot-path, called thousands
    # of times per board attempt).
    cards = analysis.cards_by_suit
    hcp_by = analysis.hcp_by_suit

    sr = std.spades
    if not (sr.min_cards <= len(cards["S"]) <= sr.max_cards):
        return False, "shape"
    if not (sr.min_hcp <= hcp_by["S"] <= sr.max_hcp):
        return False, "hcp"

    sr = std.hearts
    if not (sr.min_cards <= len(cards["H"]) <= sr.max_cards):
        return False, "shape"
    if not (sr.min_hcp <= hcp_by["H"] <= sr.max_hcp):
        return False, "hcp"

    sr = std.diamonds
    if not (sr.min_cards <= len(cards["D"]) <= sr.max_cards):
        return False, "shape"
    if not (sr.min_hcp <= hcp_by["D"] <= sr.max_hcp):
        return False, "hcp"

    sr = std.clubs
    if not (sr.min_cards <= len(cards["C"]) <= sr.max_cards):
        return False, "shape"
    if not (sr.min_hcp <= hcp_by["C"] <= sr.max_hcp):
        return False, "hcp"

    return True, None
    
    
def _match_random_suit_with_attempt(
    analysis: SuitAnalysis,
    rs: RandomSuitConstraintData,
    rng: random.Random,
    pre_selected_suits: Optional[List[str]] = None,
) -> Tuple[bool, Optional[List[str]]]:
    """
    Like _match_random_suit, but returns the attempted chosen suits even on failure.

    When pre_selected_suits is provided (from RS pre-selection in the v2
    builder), those suits are used instead of randomly sampling.  This
    ensures consistency between pre-allocation and matching.

    Returns:
      (matched, attempted_or_chosen_suits_or_None)
    """
    allowed = list(rs.allowed_suits)
    if not allowed or rs.required_suits_count <= 0:
        return False, None
    if rs.required_suits_count > len(allowed):
        return False, None

    # Use pre-committed suits when available; otherwise random sample.
    if pre_selected_suits is not None:
        chosen_suits = list(pre_selected_suits)
    else:
        chosen_suits = rng.sample(allowed, rs.required_suits_count)

    ranges_by_suit: Dict[str, SuitRange] = {}

    if rs.required_suits_count == 2 and rs.pair_overrides:
        sorted_pair = tuple(sorted(chosen_suits))
        matched_override = None
        for po in rs.pair_overrides:
            if tuple(sorted(po.suits)) == sorted_pair:
                matched_override = po
                break

        if matched_override is not None:
            ranges_by_suit[matched_override.suits[0]] = matched_override.first_range
            ranges_by_suit[matched_override.suits[1]] = matched_override.second_range
        else:
            for idx, suit in enumerate(chosen_suits):
                if idx >= len(rs.suit_ranges):
                    return False, chosen_suits
                ranges_by_suit[suit] = rs.suit_ranges[idx]
    else:
        for idx, suit in enumerate(chosen_suits):
            if idx >= len(rs.suit_ranges):
                return False, chosen_suits
            ranges_by_suit[suit] = rs.suit_ranges[idx]

    for suit in chosen_suits:
        sr = ranges_by_suit[suit]
        count = len(analysis.cards_by_suit[suit])
        hcp = analysis.hcp_by_suit[suit]
        if not (sr.min_cards <= count <= sr.max_cards):
            return False, chosen_suits
        if not (sr.min_hcp <= hcp <= sr.max_hcp):
            return False, chosen_suits

    return True, chosen_suits



def _check_suit_range(analysis: SuitAnalysis, suit: str, sr: SuitRange) -> bool:
    """Check whether a single suit in the hand satisfies a SuitRange constraint."""
    if suit not in analysis.cards_by_suit:
        return False
    count = len(analysis.cards_by_suit[suit])
    hcp = analysis.hcp_by_suit[suit]
    return sr.min_cards <= count <= sr.max_cards and sr.min_hcp <= hcp <= sr.max_hcp


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
    return _check_suit_range(analysis, partner_suits[0], pc.suit_range)

def _match_subprofile(
    analysis: SuitAnalysis,
    seat: Seat,
    sub: SubProfile,
    random_suit_choices: Dict[Seat, List[str]],
    rng: random.Random,
    pre_selected_suits: Optional[List[str]] = None,
) -> Tuple[bool, Optional[List[str]], Optional[str]]:
    """
    Attempt to match a single SubProfile to this 13-card hand.

    When pre_selected_suits is provided (from RS pre-selection in the v2
    builder), those suits are passed to the RS matcher so it uses the
    pre-committed suits instead of randomly choosing.

    Returns:
      (matched, chosen_random_suits_for_this_seat_or_None, fail_reason)

      fail_reason is one of:
        - None: matched successfully
        - "hcp": Standard HCP constraint failed
        - "shape": Standard shape constraint failed
        - "other": RS/PC/OC constraint failed (not standard)
    """
    # Always check Standard first
    std_matched, std_fail_reason = _match_standard(analysis, sub.standard)
    if not std_matched:
        return False, None, std_fail_reason

    # Random Suit (no Partner or Opponents Contingent on this seat)
    if (
        sub.random_suit_constraint is not None
        and sub.partner_contingent_constraint is None
        and sub.opponents_contingent_suit_constraint is None
    ):
        matched, chosen = _match_random_suit_with_attempt(
            analysis, sub.random_suit_constraint, rng,
            pre_selected_suits=pre_selected_suits,
        )
        if not matched:
            # Piece 3 signal: return attempted suits even on failure
            # RS failure is "other" (not standard HCP/shape)
            return False, chosen, "other"
        return True, chosen, None

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
            # PC failure is "other" (not standard HCP/shape)
            return False, None, "other"

        if _match_partner_contingent(analysis, pc, partner_suits):
            return True, None, None
        # PC constraint failed - "other" (not standard HCP/shape)
        return False, None, "other"

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
            # OC failure is "other" (not standard HCP/shape)
            return False, None, "other"

        # Opponent's Contingent Suit = first chosen suit
        if _check_suit_range(analysis, opp_suits[0], oc.suit_range):
            return True, None, None
        # OC constraint failed - "other" (not standard HCP/shape)
        return False, None, "other"

    # Standard-only sub-profile
    # (no random_suit_constraint, no partner_contingent_constraint, no opponents_contingent_suit_constraint)
    if (
        sub.random_suit_constraint is None
        and sub.partner_contingent_constraint is None
        and sub.opponents_contingent_suit_constraint is None
    ):
        return True, None, None

    # Any other combination is invalid by design; treat as not matching.
    return False, None, "other"

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
                length_eq = int(getattr(c, "length_eq", -1) or -1)
                want_count = int(getattr(c, "count", -1) or -1)

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
    rs_pre_selections: Optional[Dict[Seat, List[str]]] = None,
) -> Tuple[bool, Optional[List[str]], Optional[str]]:
    """
    Match a 13-card hand against the chosen SubProfile for a given seat.

    Logic:
      • If seat is unconstrained (no SeatProfile), accept any hand.
      • Otherwise, use the pre-selected SubProfile for this seat for the entire deal.
        We do NOT randomly switch subprofiles per attempt; uniform 1/N selection
        across deals is handled by the caller.

    When rs_pre_selections is provided (from RS pre-selection in the v2
    builder), this seat's pre-selected RS suits are threaded down to the
    RS matcher so it uses the pre-committed suits instead of random sampling.

    Returns:
      (matched, chosen_random_suits_for_this_seat_or_None, fail_reason)

      fail_reason is one of:
        - None: matched successfully
        - "hcp": Standard HCP constraint failed
        - "shape": Standard shape constraint failed
        - "other": RS/PC/OC constraint failed, or exclusion triggered
    """
    # Unconstrained seat: any 13 cards are acceptable.
    if seat_profile is None:
        return True, None, None

    # If no chosen subprofile was provided, fall back defensively to first one
    if chosen_subprofile is None:
        if not seat_profile.subprofiles:
            return True, None, None
        subprofiles: List[SubProfile] = [seat_profile.subprofiles[0]]
    else:
        subprofiles = [chosen_subprofile]

    analysis = _compute_suit_analysis(hand)

    # Extract this seat's RS pre-selection (if any) to thread down.
    seat_pre = None
    if rs_pre_selections and seat in rs_pre_selections:
        seat_pre = rs_pre_selections[seat]

    last_chosen: Optional[List[str]] = None
    last_fail_reason: Optional[str] = None

    for sub in subprofiles:
        matched, chosen, fail_reason = _match_subprofile(
            analysis=analysis,
            seat=seat,
            sub=sub,
            random_suit_choices=random_suit_choices,
            rng=rng,
            pre_selected_suits=seat_pre,
        )
        if chosen:
            last_chosen = chosen
        if fail_reason:
            last_fail_reason = fail_reason

        if matched:
            if _is_excluded_for_seat_subprofile(
                profile=profile,
                seat=seat,
                subprofile_index_1based=chosen_subprofile_index_1based,
                analysis=analysis,
            ):
                # Piece 3 signal: keep the RS choice payload even on failure.
                # Exclusion failure is "other" (not standard HCP/shape)
                return False, chosen, "other"
            return True, chosen, None

    # Piece 3 signal: if _match_subprofile produced an RS choice payload during a failed
    # attempt, return it so the caller can count this bucket as "seen".
    return False, last_chosen, last_fail_reason


# ---------------------------------------------------------------------------
# Constrained board construction (C1)
# ---------------------------------------------------------------------------


def _subprofile_is_viable_light(sub: SubProfile, *, return_reason: bool = False) -> Union[bool, Tuple[bool, str]]:
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
    if std.total_min_hcp > 37:
        ok, reason = False, f"total_min_hcp {std.total_min_hcp} > 37"
        return (ok, reason) if return_reason else ok
    if std.total_max_hcp < 0:
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
