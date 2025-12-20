# bridge_engine/deal_generator.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

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
    cards_by_suit: Dict[str, List[Card]] = {"S": [], "H": [], "D": [], "C": []}
    hcp_by_suit: Dict[str, int] = {"S": 0, "H": 0, "D": 0, "C": 0}
    total_hcp = 0

    for card in hand:
        if len(card) != 2:
            # Defensive, but we expect all cards to be rank+suit
            continue
        rank = card[0]
        suit = card[1]
        if suit not in cards_by_suit:
            continue
        cards_by_suit[suit].append(card)
        value = HCP_MAP.get(rank, 0)
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


# ---------------------------------------------------------------------------
# Constrained board construction (C1)
# ---------------------------------------------------------------------------
def _build_single_constrained_deal(
    profile: HandProfile,
    rng: random.Random,
    board_number: int,
) -> Deal:

    """
    Attempt to build a single constrained deal for the given board number.

    Rules:
      • At the start of this deal, for each constrained seat we randomly select
        exactly one SubProfile from that SeatProfile. That chosen SubProfile is
        fixed for the entire deal (all attempts for this board).
      • Hand 1: keep trying candidate hands from the full deck.
      • Hand 2 & 3: up to MAX_ATTEMPTS_HAND_2_3 candidate hands each
        from the remaining deck; if none match, restart whole board.
      • Hand 4: remaining 13 cards; if they fail constraints, restart board.
      • Overall limited by MAX_BOARD_ATTEMPTS.
    """
    dealing_order: List[Seat] = list(profile.hand_dealing_order)

    # Pre-select one SubProfile per seat (if any) for this entire deal
    chosen_subprofiles: Dict[Seat, Optional[SubProfile]] = {}
    chosen_subprofile_indices: Dict[Seat, Optional[int]] = {}
    for seat in ("N", "E", "S", "W"):
        sp = profile.seat_profiles.get(seat)
        if sp is None or not sp.subprofiles:
            chosen_subprofiles[seat] = None
            chosen_subprofile_indices[seat] = None
        else:
            # Phase 2: weighted subprofile choice using weight_percent
            weights = [float(sub.weight_percent) for sub in sp.subprofiles]

            # If the total weight is zero (e.g. profile never validated),
            # fall back to the original uniform random choice so legacy tests
            # and ad-hoc profiles still work.
            if not weights or sum(weights) <= 0.0:
                idx = rng.randrange(len(sp.subprofiles))
            else:
                idx = _weighted_choice_index(rng, weights)

            chosen_subprofiles[seat] = sp.subprofiles[idx]
            chosen_subprofile_indices[seat] = idx
 
    # ------------------------------------------------------------------
    # F3: Opener → responder sub-profile coupling (NS driver/follower)
    #
    # If a partnership has multiple sub-profiles on both seats AND the counts
    # match, force the responder's chosen sub-profile index to equal the
    # opener's.
    #
    # For NS, the *driver* seat is chosen by HandProfile.ns_driver_seat(...)
    # (which in turn consults ns_role_mode). For EW we keep the fixed
    # E-opens / W-responds behaviour from Phase 2.
    #
    # Rotation is a post-dealing concern and is unaffected by this coupling.
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
        # Defensive: if ns_role_mode is mis-set, fall back.
        ns_driver = "N"

    ns_responder: Seat = "S" if ns_driver == "N" else "N"
    _apply_pair_coupling(ns_driver, ns_responder)

    # EW: keep legacy behaviour – East is opener, West is responder.
    _apply_pair_coupling("E", "W")

    board_attempts = 0    
    while board_attempts < MAX_BOARD_ATTEMPTS:
        board_attempts += 1

        deck = _build_deck()
        rng.shuffle(deck)
        remaining = list(deck)
        hands: Dict[Seat, List[Card]] = {}
        random_suit_choices: Dict[Seat, List[str]] = {}

        success_for_board = True

        for idx, seat in enumerate(dealing_order):
            seat_profile = profile.seat_profiles.get(seat)
            sub_for_seat = chosen_subprofiles.get(seat)

            # How many cards to draw: always 13
            if idx < 3:
                # Seats 0,1,2: we choose 13 from the current remaining cards.
                # For hand 1: unlimited tries (bounded by MAX_BOARD_ATTEMPTS).
                # For hand 2 & 3: up to MAX_ATTEMPTS_HAND_2_3 tries.
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
                    # Sample 13 cards from remaining
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
                    success_for_board = False
                    break

                # Commit chosen hand: remove cards from remaining
                hands[seat] = chosen_hand
                for card in chosen_hand:
                    remaining.remove(card)  # will raise if card missing, which is fine

                if chosen_random_suits_for_seat is not None:
                    random_suit_choices[seat] = chosen_random_suits_for_seat

            else:
                # idx == 3: last seat gets remaining 13 cards
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
                    success_for_board = False
                    break
                hands[seat] = candidate
                if chosen is not None:
                    random_suit_choices[seat] = chosen
                remaining.clear()

        if success_for_board and len(hands) == 4:
            # All four seats succeeded – optional diagnostic print for chosen subprofiles
            if DEBUG_SECTION_C:
                print(
                    f"[DEBUG] Board {board_number} subprofile choices: "
                    f"N={chosen_subprofile_indices.get('N')}, "
                    f"E={chosen_subprofile_indices.get('E')}, "
                    f"S={chosen_subprofile_indices.get('S')}, "
                    f"W={chosen_subprofile_indices.get('W')}"
                )

            return Deal(
                board_number=board_number,
                dealer=profile.dealer,
                vulnerability="None",  # will be enriched in C2
                hands=hands,
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