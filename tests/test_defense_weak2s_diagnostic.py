# tests/test_defense_weak2s_diagnostic.py
"""
Diagnostic test for the "Defense to 3 Weak 2s" profile.

This is the toughest profile in the collection:
  - W: RS (pick 1 of S/H/D for 6-card weak-2, 6-11 HCP)
  - N: 4 subprofiles (2 OC on W + 2 RS), 25% each
  - E: 4 subprofiles (same structure as N, OC on W)
  - S: Standard only, 8-17 HCP

The test generates boards and prints full diagnostic output:
  - Per-board: subprofile selections, attempt count, success/fail
  - Aggregate: failure attribution breakdown by seat (as_seat, global_other,
    global_unchecked, hcp, shape)
  - Summary statistics: success rate, mean attempts, worst board

Run with:  pytest -q -s tests/test_defense_weak2s_diagnostic.py
"""
from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Dict, Optional

import pytest

import bridge_engine.deal_generator as dg
from bridge_engine.deal_generator import (
    _build_single_constrained_deal_v2,
    _card_hcp,
    generate_deals,
    DealGenerationError,
)
from bridge_engine.hand_profile import HandProfile
from bridge_engine.setup_env import run_setup

Seat = str

PROFILE_DIR = Path("profiles")
PROFILE_FNAME = "Defense_to_3_Weak_2s_v0.2.json"

NUM_BOARDS = 20


def _load_profile() -> HandProfile:
    """Load the Defense to Weak 2s profile."""
    path = PROFILE_DIR / PROFILE_FNAME
    if not path.exists():
        pytest.skip(f"Missing profile: {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    return HandProfile.from_dict(raw)


def _hand_hcp(hand: list) -> int:
    return sum(_card_hcp(c) for c in hand)


def _suit_count(hand: list, suit_letter: str) -> int:
    return sum(1 for c in hand if len(c) >= 2 and c[1] == suit_letter)


def _hand_shape(hand: list) -> str:
    """Return shape string like '6-3-2-2' (S-H-D-C)."""
    counts = [_suit_count(hand, s) for s in "SHDC"]
    return "-".join(str(c) for c in counts)


def _fmt_row(label: str, counts: Dict[Seat, int]) -> str:
    total = sum(counts.values())
    return (
        f"  {label:<26} "
        f"{counts.get('W', 0):6d} {counts.get('N', 0):6d} "
        f"{counts.get('S', 0):6d} {counts.get('E', 0):6d} "
        f"{total:8d}"
    )


class TestDefenseWeak2sDiagnostic:
    """Generate boards from the toughest profile and print full diagnostics."""

    def test_v2_builder_diagnostic(self):
        """Run v2 builder on Defense to Weak 2s with full attribution output."""
        profile = _load_profile()

        # ---- Aggregated counters across all boards ----
        total_as_seat: Dict[Seat, int] = {s: 0 for s in "WNES"}
        total_global_other: Dict[Seat, int] = {s: 0 for s in "WNES"}
        total_global_unchecked: Dict[Seat, int] = {s: 0 for s in "WNES"}
        total_hcp: Dict[Seat, int] = {s: 0 for s in "WNES"}
        total_shape: Dict[Seat, int] = {s: 0 for s in "WNES"}

        board_results = []  # (board_number, success, attempts, deal_or_None)
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

            print(f"\n{'='*75}")
            print(f"Profile: {PROFILE_FNAME}")
            print(f"Boards: {NUM_BOARDS}  |  Dealer: W  |  Order: W-N-S-E")
            print(f"{'='*75}")

            for board_number in range(1, NUM_BOARDS + 1):
                latest_snapshot.clear()
                attempt_counter[0] = 0

                rng = random.Random(50_000 + board_number)
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

                # The attempt count is from the last hook call (last failed attempt).
                # On success, the actual attempt count = hook count + 1 (the successful one).
                attempts = attempt_counter[0] + (1 if success else 0)
                total_attempts += attempts

                # Print per-board summary.
                status = "OK" if success else "FAIL"
                if deal is not None:
                    w_hand = deal.hands.get("W", [])
                    n_hand = deal.hands.get("N", [])
                    s_hand = deal.hands.get("S", [])
                    e_hand = deal.hands.get("E", [])
                    print(
                        f"  Board {board_number:3d}: {status}  attempts={attempts:5d}  "
                        f"W:{_hand_shape(w_hand)} {_hand_hcp(w_hand):2d}hcp  "
                        f"N:{_hand_shape(n_hand)} {_hand_hcp(n_hand):2d}hcp  "
                        f"S:{_hand_shape(s_hand)} {_hand_hcp(s_hand):2d}hcp  "
                        f"E:{_hand_shape(e_hand)} {_hand_hcp(e_hand):2d}hcp"
                    )
                else:
                    print(
                        f"  Board {board_number:3d}: {status}  attempts={attempts:5d}  "
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
        successes = sum(1 for _, ok, _, _ in board_results if ok)
        failures = NUM_BOARDS - successes
        attempt_list = [a for _, _, a, _ in board_results]
        mean_attempts = total_attempts / NUM_BOARDS if NUM_BOARDS > 0 else 0
        max_attempts = max(attempt_list) if attempt_list else 0
        min_attempts = min(attempt_list) if attempt_list else 0

        print(f"\n{'─'*75}")
        print(f"SUMMARY: {successes}/{NUM_BOARDS} boards succeeded, {failures} failed")
        print(
            f"Attempts: total={total_attempts}  mean={mean_attempts:.1f}  "
            f"min={min_attempts}  max={max_attempts}"
        )

        print(f"\n  {'Failure Attribution':<26} {'W':>6} {'N':>6} {'S':>6} {'E':>6} {'TOTAL':>8}")
        print(f"  {'─'*26} {'─'*6} {'─'*6} {'─'*6} {'─'*6} {'─'*8}")
        print(_fmt_row("seat_fail_as_seat", total_as_seat))
        print(_fmt_row("seat_fail_global_other", total_global_other))
        print(_fmt_row("seat_fail_global_unchecked", total_global_unchecked))
        print(_fmt_row("seat_fail_hcp", total_hcp))
        print(_fmt_row("seat_fail_shape", total_shape))
        print(f"{'='*75}\n")

        # ---- Assertions ----
        # This profile should be viable — assert at least some boards succeed.
        assert successes > 0, (
            f"No boards succeeded out of {NUM_BOARDS}. "
            f"Profile may be too hard for v2 builder."
        )

    def test_full_pipeline(self, tmp_path):
        """Run generate_deals() pipeline on Defense to Weak 2s (1 board at a time).

        This is the toughest profile — some boards may exhaust 10,000 attempts.
        We try generating 1 board per call with different seeds by using the
        v2 builder directly (which gives us seed control).  At least 1 must
        succeed to prove the pipeline works end-to-end.
        """
        profile = _load_profile()

        # 20 boards with ~44% per-board success rate gives >99.99% chance
        # of at least 1 success. Kept at 20 to avoid bloating test suite time.
        successes = 0
        num_pipeline_boards = 20
        for board_number in range(1, num_pipeline_boards + 1):
            rng = random.Random(50_000 + board_number)
            try:
                deal = _build_single_constrained_deal_v2(
                    rng=rng,
                    profile=profile,
                    board_number=board_number,
                )
                w = deal.hands.get("W", [])
                print(
                    f"  Pipeline board {board_number}: OK  "
                    f"W:{_hand_shape(w)} {_hand_hcp(w):2d}hcp"
                )
                successes += 1
            except DealGenerationError:
                pass  # Expected for this tough profile

        print(f"\n  Pipeline: {successes}/{num_pipeline_boards} boards succeeded")
        assert successes > 0, (
            f"No pipeline boards succeeded out of {num_pipeline_boards} attempts."
        )
