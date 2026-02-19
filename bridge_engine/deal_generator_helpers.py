# bridge_engine/deal_generator_helpers.py
#
# Shared utility functions extracted from deal_generator.py as part of
# the #7 refactor.
#
# Contains: viability helpers, subprofile selection, deck helpers,
# HCP utilities, simple board generator, and
# vulnerability/rotation enrichment.
from __future__ import annotations

import math
import random
from typing import Dict, List, Sequence, Tuple

from .deal_generator_types import (
    Seat,
    Card,
    SeatFailCounts,
    SeatSeenCounts,
    Deal,
    VULNERABILITY_SEQUENCE,
    ROTATE_MAP,
    ROTATE_PROBABILITY,
    HCP_FEASIBILITY_NUM_SD,
    _MASTER_DECK,
    _CARD_HCP,
)
from .hand_profile import (
    SeatProfile,
)


# ---------------------------------------------------------------------------
# Viability helpers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Subprofile helpers
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


# NOTE: _select_subprofiles_for_board lives in deal_generator.py (not here)
# because it uses isinstance(x, SeatProfile) checks, and several tests
# monkeypatch deal_generator.SeatProfile with dummy classes.

# ---------------------------------------------------------------------------
# Deck helpers
# ---------------------------------------------------------------------------


def _build_deck() -> List[Card]:
    """Return a fresh copy of the 52-card master deck."""
    return list(_MASTER_DECK)


# ---------------------------------------------------------------------------
# HCP utilities
# ---------------------------------------------------------------------------


def _card_hcp(card: Card) -> int:
    """
    Return the HCP (high card points) value of a single card.

    A=4, K=3, Q=2, J=1, all others=0.  Card format is rank+suit, e.g. "AS".
    Uses pre-built _CARD_HCP dict for O(1) lookup without function-call overhead
    on the hot path.  Callers in tight loops should use _CARD_HCP[card] directly.
    """
    if not card:
        return 0
    return _CARD_HCP.get(card, 0)


def _deck_hcp_stats(deck: List[Card]) -> Tuple[int, int]:
    """
    Compute aggregate HCP statistics for a deck (or partial deck) of cards.

    Returns (hcp_sum, hcp_sum_sq) in a single pass:
      hcp_sum    — total HCP across all cards
      hcp_sum_sq — sum of squared HCP values (needed for variance calculation)

    For a full 52-card deck: hcp_sum = 40, hcp_sum_sq = 120.
    """
    hcp_sum = 0
    hcp_sum_sq = 0
    card_hcp = _CARD_HCP  # local alias avoids repeated global lookup
    for card in deck:
        v = card_hcp[card]
        hcp_sum += v
        hcp_sum_sq += v * v
    return hcp_sum, hcp_sum_sq


def _check_hcp_feasibility(
    drawn_hcp: int,
    cards_remaining: int,
    deck_size: int,
    deck_hcp_sum: int,
    deck_hcp_sum_sq: int,
    target_min: int,
    target_max: int,
    num_sd: float = HCP_FEASIBILITY_NUM_SD,
) -> bool:
    """
    Check whether a target HCP range is still achievable given what has been
    drawn so far and the composition of the remaining deck.

    Args:
        drawn_hcp:       HCP already committed to this hand.
        cards_remaining: Number of cards still to be dealt to this hand.
        deck_size:       Number of cards currently in the deck.
        deck_hcp_sum:    Sum of HCP values of cards in the deck.
        deck_hcp_sum_sq: Sum of squared HCP values of cards in the deck.
        target_min:      Minimum acceptable total HCP for the hand.
        target_max:      Maximum acceptable total HCP for the hand.
        num_sd:          Number of standard deviations for the confidence band.

    Returns:
        True  — target range is still plausible (don't reject).
        False — target range is statistically implausible (reject this hand).
    """
    # ---- Edge case: hand is complete ----
    if cards_remaining <= 0:
        return target_min <= drawn_hcp <= target_max

    # ---- Edge case: deck too small for a meaningful variance calc ----
    if deck_size <= 0:
        # No cards left to draw — compare what we have.
        return target_min <= drawn_hcp <= target_max

    # ---- Population mean and variance of remaining deck ----
    mu = deck_hcp_sum / deck_size
    sigma_sq = deck_hcp_sum_sq / deck_size - mu * mu

    # ---- Expected additional HCP ----
    expected_additional = cards_remaining * mu
    expected_total = drawn_hcp + expected_additional

    # ---- Variance of additional HCP (finite population correction) ----
    if deck_size <= 1:
        # Only one card remains — no variance; we'll draw it deterministically.
        var_additional = 0.0
    else:
        fpc = (deck_size - cards_remaining) / (deck_size - 1)
        var_additional = cards_remaining * sigma_sq * fpc

    sd_additional = math.sqrt(max(0.0, var_additional))

    # ---- Confidence interval for total HCP ----
    exp_down = expected_total - num_sd * sd_additional
    exp_up = expected_total + num_sd * sd_additional

    # ---- Feasibility test ----
    # Reject if even the favourable end of the prediction can't reach the target.
    if exp_down > target_max:
        return False  # Already too high — even low-side can't stay under max.
    if exp_up < target_min:
        return False  # Too low — even high-side can't reach min.
    return True


# ---------------------------------------------------------------------------
# Simple board generator (fallback for tests / dummy profiles)
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


def _vulnerability_for_board(board_number: int) -> str:
    """Return the cyclic vulnerability string for a 1-based board number."""
    return VULNERABILITY_SEQUENCE[(board_number - 1) % len(VULNERABILITY_SEQUENCE)]


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
