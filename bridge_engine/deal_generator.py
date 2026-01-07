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
from .seat_viability import _match_seat


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


def _build_single_constrained_deal(
    rng: random.Random,    
    profile: HandProfile,
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

        # ------------------------------------------------------------------
        # NS driver/follower semantics + sub-profile index matching
        #
        # We derive a per-board NS driver seat from ns_role_mode, then
        # treat the other NS seat as follower. SubProfile.ns_role_usage
        # is interpreted as:
        #   - "any"           → allowed in both roles
        #   - "driver_only"   → only when this seat is the driver
        #   - "follower_only" → only when this seat is the follower
        #
        # The older behaviour called “F3 coupling” in the tests is now
        # described as NS sub-profile index matching: once the driver
        # seat has chosen a sub-profile index, the follower seat uses
        # the same index when picking its own sub-profile. That behaviour
        # is still in place; later upgrades may make it conditional on
        # ns_role_mode (e.g. disabled when an explicit driver is set).
        # -----------------------------------------------------------------
        
    # NS driver/follower semantics for subprofile selection
    #
    # ns_role_mode controls how (and whether) we treat one NS seat as a
    # "driver" and the other as "follower".
    #
    # For most modes ("north_drives", "south_drives", "random_driver"),
    # we keep the existing index-matching behaviour (formerly F3
    # coupling): one NS seat is the driver and the partner follows the
    # same subprofile index.
    #
    # For ns_role_mode == "no_driver_no_index" we *disable* NS driver
    # semantics entirely. N and S will each pick subprofiles
    # independently, just like E/W, with no index matching.
    # ------------------------------------------------------------------
    mode = (getattr(profile, "ns_role_mode", "north_drives") or "north_drives").lower()

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
        chosen_subprofiles, chosen_subprofile_indices = _select_subprofiles_for_board()
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
