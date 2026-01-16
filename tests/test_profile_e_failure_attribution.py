import json
import os
import random
from pathlib import Path
from typing import Dict

import pytest

import bridge_engine.deal_generator as dg
from bridge_engine.hand_profile import HandProfile

Seat = str

PROFILE_DIR = Path("profiles")
PROFILE_E_FNAME = "Profile_E_Test_-_tight_and_suit_point_constraint_plus_v0.1.json"


def _load_profile(path: Path) -> HandProfile:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return HandProfile.from_dict(raw)


def _fmt_row(label: str, counts: Dict[Seat, int]) -> str:
    total = sum(counts.values())
    return (
        f"{label:<24} "
        f"{counts['N']:7d} {counts['E']:7d} {counts['S']:7d} {counts['W']:7d} "
        f"{total:9d}"
    )


@pytest.mark.skipif(
    not os.getenv("RUN_PROFILE_E_ATTRIBUTION"),
    reason="Opt-in benchmark. Run with RUN_PROFILE_E_ATTRIBUTION=1 pytest -q -s tests/test_profile_e_failure_attribution.py",
)
def test_profile_e_failure_attribution_summary() -> None:
    """
    For Profile E, accumulate per-seat failure attribution across a number of boards.

    We:
      * run the internal constrained builder directly,
      * let the debug hook expose attempt-level failure attribution,
      * keep the final cumulative snapshot per board,
      * then sum those across all boards for a coarse "pain map".
    """
    path = PROFILE_DIR / PROFILE_E_FNAME
    if not path.exists():
        pytest.skip(f"Missing profile file: {path}")

    profile = _load_profile(path)

    # How many boards to sample.
    num_boards = 200

    # Aggregates across boards (final per-board snapshot).
    total_as_seat: Dict[Seat, int] = {"N": 0, "E": 0, "S": 0, "W": 0}
    total_global_other: Dict[Seat, int] = {"N": 0, "E": 0, "S": 0, "W": 0}
    total_global_unchecked: Dict[Seat, int] = {"N": 0, "E": 0, "S": 0, "W": 0}
    total_hcp: Dict[Seat, int] = {"N": 0, "E": 0, "S": 0, "W": 0}
    total_shape: Dict[Seat, int] = {"N": 0, "E": 0, "S": 0, "W": 0}

    board_success = 0
    board_fail = 0

    # Preserve any existing hook.
    old_hook = getattr(dg, "_DEBUG_ON_ATTEMPT_FAILURE_ATTRIBUTION", None)

    try:
        for board_number in range(1, num_boards + 1):
            # Attempt-local “latest snapshot” (cumulative for this board).
            latest_as_seat: Dict[Seat, int] = {}
            latest_global_other: Dict[Seat, int] = {}
            latest_global_unchecked: Dict[Seat, int] = {}
            latest_hcp: Dict[Seat, int] = {}
            latest_shape: Dict[Seat, int] = {}

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
                nonlocal latest_as_seat, latest_global_other, latest_global_unchecked, latest_hcp, latest_shape
                # Snapshot the cumulative totals for this board as of this failed attempt.
                latest_as_seat = dict(seat_fail_as_seat)
                latest_global_other = dict(seat_fail_global_other)
                latest_global_unchecked = dict(seat_fail_global_unchecked)
                latest_hcp = dict(seat_fail_hcp)
                latest_shape = dict(seat_fail_shape)
                
                # Snapshot the cumulative totals for this board as of this failed attempt.
                latest_as_seat = dict(seat_fail_as_seat)
                latest_global_other = dict(seat_fail_global_other)
                latest_global_unchecked = dict(seat_fail_global_unchecked)
                latest_hcp = dict(seat_fail_hcp)
                latest_shape = dict(seat_fail_shape)

            dg._DEBUG_ON_ATTEMPT_FAILURE_ATTRIBUTION = hook

            # Deterministic per-board RNG so this is reproducible.
            rng = random.Random(10_000 + board_number)
            try:
                # Call the constrained builder directly so we get per-board attribution.
                dg._build_single_constrained_deal(
                    rng=rng,
                    profile=profile,
                    board_number=board_number,
                )
                board_success += 1
            except dg.DealGenerationError:
                board_fail += 1

            # Accumulate the last seen snapshot for this board (may be empty if no failures).
            for k, v in latest_as_seat.items():
                total_as_seat[k] = total_as_seat.get(k, 0) + int(v)
            for k, v in latest_global_other.items():
                total_global_other[k] = total_global_other.get(k, 0) + int(v)
            for k, v in latest_global_unchecked.items():
                total_global_unchecked[k] = total_global_unchecked.get(k, 0) + int(v)
            for k, v in latest_hcp.items():
                total_hcp[k] = total_hcp.get(k, 0) + int(v)
            for k, v in latest_shape.items():
                total_shape[k] = total_shape.get(k, 0) + int(v)

    finally:
        dg._DEBUG_ON_ATTEMPT_FAILURE_ATTRIBUTION = old_hook

    # ---- Print summary ----
    print(f"\nProfile E: {PROFILE_E_FNAME}")
    print(f"Boards: {num_boards}   success={board_success}   fail={board_fail}")
    print("")
    print(f"{'bucket':<24} {'N':>7} {'E':>7} {'S':>7} {'W':>7} {'TOTAL':>9}")
    print("-" * 24 + " " + "-" * (7 * 4 + 1 * 4 + 9))
    print(_fmt_row("seat_fail_as_seat", total_as_seat))
    print(_fmt_row("seat_global_other", total_global_other))
    print(_fmt_row("seat_global_unchecked", total_global_unchecked))

    total_hcp_sum = sum(total_hcp.values())
    total_shape_sum = sum(total_shape.values())

    print(
        f"seat_fail_hcp              {total_hcp['N']:7d} {total_hcp['E']:7d} "
        f"{total_hcp['S']:7d} {total_hcp['W']:7d} {total_hcp_sum:9d}"
    )
    print(
        f"seat_fail_shape            {total_shape['N']:7d} {total_shape['E']:7d} "
        f"{total_shape['S']:7d} {total_shape['W']:7d} {total_shape_sum:9d}"
    )
    print("")