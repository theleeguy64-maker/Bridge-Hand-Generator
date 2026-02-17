# bridge_engine/profile_diagnostic.py
#
# Generic profile diagnostic runner.
#
# Runs the v2 builder on any profile and prints per-board results plus
# aggregate failure attribution.  Accessible from the Admin menu.
#
# Based on the approach in tests/test_defense_weak2s_diagnostic.py,
# but generalised for any HandProfile.
from __future__ import annotations

import random
import time
from typing import Dict, List

from . import deal_generator as dg
from .deal_generator import (
    _build_single_constrained_deal_v2,
    _card_hcp,
    DealGenerationError,
)

Seat = str


# ---------------------------------------------------------------------------
# Hand display helpers
# ---------------------------------------------------------------------------


def _hand_hcp(hand: list) -> int:
    """Sum HCP for a hand (list of card strings like 'AS', '2H')."""
    return sum(_card_hcp(c) for c in hand)


def _suit_count(hand: list, suit_letter: str) -> int:
    """Count cards belonging to a suit (S/H/D/C)."""
    return sum(1 for c in hand if len(c) >= 2 and c[1] == suit_letter)


def _hand_shape(hand: list) -> str:
    """Return shape string like '6-3-2-2' (S-H-D-C order)."""
    counts = [_suit_count(hand, s) for s in "SHDC"]
    return "-".join(str(c) for c in counts)


def _fmt_row(label: str, counts: Dict[Seat, int]) -> str:
    """Format one row of the failure attribution table with counts and %."""
    total = sum(counts.values())
    parts = []
    for seat in ("W", "N", "S", "E"):
        cnt = counts.get(seat, 0)
        pct = (cnt / total * 100) if total > 0 else 0.0
        parts.append(f"{cnt:6d} ({pct:4.1f}%)")
    return f"  {label:<26} " + " ".join(parts) + f" {total:8d}"


# ---------------------------------------------------------------------------
# Main diagnostic runner
# ---------------------------------------------------------------------------


def run_profile_diagnostic(
    profile,
    num_boards: int = 20,
    seed_base: int = 50_000,
) -> None:
    """
    Run the v2 builder on *profile* for *num_boards* boards and print
    detailed failure attribution diagnostics.

    Output:
      - Per-board line: board number, OK/FAIL, attempt count, per-seat shape+HCP
      - Aggregate failure attribution table (5 categories x 4 seats)
      - Attempt statistics (total, mean, min, max)

    The debug hook ``_DEBUG_ON_ATTEMPT_FAILURE_ATTRIBUTION`` is temporarily
    installed on the deal_generator module and restored afterwards.
    """
    profile_name = profile.profile_name

    # ---- Aggregated counters across all boards ----
    total_as_seat: Dict[Seat, int] = {s: 0 for s in ("W", "N", "E", "S")}
    total_global_other: Dict[Seat, int] = {s: 0 for s in ("W", "N", "E", "S")}
    total_global_unchecked: Dict[Seat, int] = {s: 0 for s in ("W", "N", "E", "S")}
    total_hcp: Dict[Seat, int] = {s: 0 for s in ("W", "N", "E", "S")}
    total_shape: Dict[Seat, int] = {s: 0 for s in ("W", "N", "E", "S")}

    board_results: List[tuple] = []  # (board_number, success, attempts, deal_or_None)
    total_attempts = 0

    # ---- Hook to capture per-attempt attribution ----
    latest_snapshot: Dict[str, Dict[Seat, int]] = {}
    attempt_counter = [0]

    def hook(
        _profile,
        _board_number: int,
        _attempt_number: int,
        seat_fail_as_seat: Dict[Seat, int],
        seat_fail_global_other: Dict[Seat, int],
        seat_fail_global_unchecked: Dict[Seat, int],
        seat_fail_hcp: Dict[Seat, int],
        seat_fail_shape: Dict[Seat, int],
    ) -> None:
        latest_snapshot["as_seat"] = dict(seat_fail_as_seat)
        latest_snapshot["global_other"] = dict(seat_fail_global_other)
        latest_snapshot["global_unchecked"] = dict(seat_fail_global_unchecked)
        latest_snapshot["hcp"] = dict(seat_fail_hcp)
        latest_snapshot["shape"] = dict(seat_fail_shape)
        attempt_counter[0] = _attempt_number

    old_hook = getattr(dg, "_DEBUG_ON_ATTEMPT_FAILURE_ATTRIBUTION", None)

    try:
        dg._DEBUG_ON_ATTEMPT_FAILURE_ATTRIBUTION = hook

        print(f"\n{'=' * 75}")
        print(f"Profile Diagnostic: {profile_name}")
        print(f"Boards: {num_boards}  |  Seed base: {seed_base}")
        print(f"{'=' * 75}")

        wall_start = time.monotonic()

        for board_number in range(1, num_boards + 1):
            latest_snapshot.clear()
            attempt_counter[0] = 0

            rng = random.Random(seed_base + board_number)
            success = True
            deal = None

            try:
                deal = _build_single_constrained_deal_v2(
                    rng=rng,
                    profile=profile,
                    board_number=board_number,
                )
            except DealGenerationError:
                success = False

            # Attempt count: hook tracks failed attempts; add 1 for the
            # successful attempt itself.
            attempts = attempt_counter[0] + (1 if success else 0)
            total_attempts += attempts

            # ---- Print per-board summary ----
            status = "OK" if success else "FAIL"
            if deal is not None:
                parts = []
                for seat in ("W", "N", "S", "E"):
                    hand = deal.hands.get(seat, [])
                    parts.append(f"{seat}:{_hand_shape(hand)} {_hand_hcp(hand):2d}hcp")
                print(f"  Board {board_number:3d}: {status}  attempts={attempts:5d}  " + "  ".join(parts))
            else:
                print(
                    f"  Board {board_number:3d}: {status}  "
                    f"attempts={attempts:5d}  "
                    f"(exhausted {dg.MAX_BOARD_ATTEMPTS} attempts)"
                )

            board_results.append((board_number, success, attempts, deal))

            # Accumulate attribution from last snapshot.
            for key, agg in [
                ("as_seat", total_as_seat),
                ("global_other", total_global_other),
                ("global_unchecked", total_global_unchecked),
                ("hcp", total_hcp),
                ("shape", total_shape),
            ]:
                for seat, val in latest_snapshot.get(key, {}).items():
                    agg[seat] = agg.get(seat, 0) + int(val)

    finally:
        dg._DEBUG_ON_ATTEMPT_FAILURE_ATTRIBUTION = old_hook

    # ---- Print aggregate summary ----
    wall_elapsed = time.monotonic() - wall_start
    successes = sum(1 for _, ok, _, _ in board_results if ok)
    failures = num_boards - successes
    attempt_list = [a for _, _, a, _ in board_results]
    mean_attempts = total_attempts / num_boards if num_boards > 0 else 0
    max_attempts = max(attempt_list) if attempt_list else 0
    min_attempts = min(attempt_list) if attempt_list else 0

    print(f"\n{'─' * 75}")
    print(f"SUMMARY: {successes}/{num_boards} boards succeeded, {failures} failed")
    print(f"Attempts: total={total_attempts}  mean={mean_attempts:.1f}  min={min_attempts}  max={max_attempts}")
    print(f"Wall time: {wall_elapsed:.1f}s")

    # Column widths: label=26, each seat=13 "NNNNNN (NN.N%)", total=8
    col = 13  # width per seat column
    print(f"\n  {'Failure Attribution':<26} {'W':>{col}} {'N':>{col}} {'S':>{col}} {'E':>{col}} {'TOTAL':>8}")
    print(f"  {'─' * 26} {'─' * col} {'─' * col} {'─' * col} {'─' * col} {'─' * 8}")
    print(_fmt_row("seat_fail_as_seat", total_as_seat))
    print(_fmt_row("seat_fail_global_other", total_global_other))
    print(_fmt_row("seat_fail_global_unchecked", total_global_unchecked))
    print(_fmt_row("seat_fail_hcp", total_hcp))
    print(_fmt_row("seat_fail_shape", total_shape))

    # ---- Seat ranking by primary failures (as_seat) ----
    # Rank seats from most to least failures, showing count and % of total.
    as_seat_total = sum(total_as_seat.values())
    if as_seat_total > 0:
        ranked = sorted(total_as_seat.items(), key=lambda x: x[1], reverse=True)
        print("\n  Seat ranking (by primary failures):")
        for rank, (seat, cnt) in enumerate(ranked, 1):
            pct = cnt / as_seat_total * 100
            print(f"    {rank}. {seat}  {cnt:6d}  ({pct:.1f}%)")

    print(f"\n{'=' * 75}\n")
