# tests/test_profile_e_rotation_rank_helper_seat.py

from pathlib import Path
from typing import Dict, Optional

import json
import random
import os
import pytest

import bridge_engine.deal_generator as dg
from bridge_engine.hand_profile import HandProfile

Seat = str

PROFILE_DIR = Path("profiles")
PROFILE_E = "Profile_E_Test_-_tight_and_suit_point_constraint_plus_v0.1.json"


# This is a benchmark-style test; keep it opt-in so the normal suite stays fast.
if os.environ.get("RUN_PROFILE_E_ROTATION_RANK", "") != "1":
    pytest.skip(
        "Opt-in benchmark. Run with RUN_PROFILE_E_ROTATION_RANK=1 pytest -q -s tests/test_profile_e_rotation_rank_helper_seat.py",
        allow_module_level=True,
    )
    
    
# Helper-seat analysis logic for local-attempt stats.
def _analyse_helper_seat_from_fail_stats(
    seat_fail_as_seat: Dict[Seat, int],
    attempt_fail_events: int,
    *,
    min_pain_share: float = 0.25,
    dominance_factor: float = 2.0,
) -> Dict[str, object]:
    """
    Decide whether this profile should have a helper seat, based purely on
    local seat-level failure attribution (seat_fail_as_seat) across many
    attempts with rotated dealing order.

    Returns a dict with:
      - mode: "no_helper" | "helper" | "trivial"
      - helper_seat: "N"/"E"/"S"/"W"/None
      - pain_share: dict seat->float (sum ≈ 1.0 if attempt_fail_events>0)
      - p_star: float (worst seat's pain share)
      - seat_star: worst seat
      - reason: short string
    """
    seats: tuple[Seat, ...] = ("N", "E", "S", "W")

    if attempt_fail_events <= 0:
        # No failed attempts at all – profile is trivially easy; no helper.
        pain_share = {s: 0.0 for s in seats}
        return {
            "mode": "trivial",
            "helper_seat": None,
            "pain_share": pain_share,
            "p_star": 0.0,
            "seat_star": None,
            "reason": "no_failed_attempts",
        }

    # Pain share p_s = seat_fail_as_seat[s] / attempt_fail_events.
    pain_share: Dict[Seat, float] = {}
    for s in seats:
        pain_share[s] = float(seat_fail_as_seat.get(s, 0)) / float(
            attempt_fail_events
        )

    # Worst seat by pain share.
    seat_star: Seat = max(seats, key=lambda s: pain_share[s])
    p_star = pain_share[seat_star]

    # Threshold corresponding to "twice as bad as the other three combined".
    # dominance_factor = 2.0 => dominance_threshold = 2 / (1 + 2) = 2/3 ≈ 0.67
    dominance_threshold = dominance_factor / (1.0 + dominance_factor)

    # 1) Ignore if pain share is too small to matter.
    if p_star < min_pain_share:
        return {
            "mode": "no_helper",
            "helper_seat": None,
            "pain_share": pain_share,
            "p_star": p_star,
            "seat_star": seat_star,
            "reason": "pain_share_below_threshold",
        }

    # 2) If worst seat is at least ~2/3 of all failures, treat as bottleneck.
    if p_star >= dominance_threshold:
        return {
            "mode": "helper",
            "helper_seat": seat_star,
            "pain_share": pain_share,
            "p_star": p_star,
            "seat_star": seat_star,
            "reason": "dominant_bottleneck",
        }

    # 3) Otherwise, we don't assign a helper seat – pain is too spread out.
    return {
        "mode": "no_helper",
        "helper_seat": None,
        "pain_share": pain_share,
        "p_star": p_star,
        "seat_star": seat_star,
        "reason": "not_dominant_enough",
    }


def _load_profile(path: Path) -> HandProfile:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return HandProfile.from_dict(raw)


def _rotate(order, k: int):
    k = k % len(order)
    return list(order[k:]) + list(order[:k])


@pytest.mark.slow
def test_profile_e_rotation_rank_helper_seat(capsys) -> None:
    path = PROFILE_DIR / PROFILE_E
    if not path.exists():
        pytest.skip(f"Missing profile file: {path}")

    profile = _load_profile(path)

    RUNS = 4
    BOARDS_PER_RUN = 50
    MAX_ATTEMPTS = 500

    # Save/restore global + profile mutation
    old_max_attempts = dg.MAX_BOARD_ATTEMPTS
    original_dealing_order = list(profile.hand_dealing_order)

    # Totals across all failed attempts across all boards.
    seat_fail_as_seat: Dict[Seat, int] = {"N": 0, "E": 0, "S": 0, "W": 0}
    seat_fail_global_other: Dict[Seat, int] = {"N": 0, "E": 0, "S": 0, "W": 0}
    seat_fail_global_unchecked: Dict[Seat, int] = {"N": 0, "E": 0, "S": 0, "W": 0}

    attempt_fail_events = 0
    boards_failed = 0

    # Track per-board previous cumulative counters so we can delta them.
    last_board_number: Optional[int] = None
    prev_as: Dict[Seat, int] = {"N": 0, "E": 0, "S": 0, "W": 0}
    prev_other: Dict[Seat, int] = {"N": 0, "E": 0, "S": 0, "W": 0}
    prev_unchecked: Dict[Seat, int] = {"N": 0, "E": 0, "S": 0, "W": 0}

    def hook(_profile, _board_number, _attempt_number, d_as, d_other, d_unchecked):
        nonlocal attempt_fail_events, last_board_number, prev_as, prev_other, prev_unchecked

        attempt_fail_events += 1

        # New board => reset "previous" snapshots (counters restart each board).
        if last_board_number != _board_number:
            last_board_number = _board_number
            prev_as = {"N": 0, "E": 0, "S": 0, "W": 0}
            prev_other = {"N": 0, "E": 0, "S": 0, "W": 0}
            prev_unchecked = {"N": 0, "E": 0, "S": 0, "W": 0}

        # Delta = current cumulative - previous cumulative
        for s in ("N", "E", "S", "W"):
            cur_as = int(d_as.get(s, 0))
            cur_other = int(d_other.get(s, 0))
            cur_unchecked = int(d_unchecked.get(s, 0))

            seat_fail_as_seat[s] += max(0, cur_as - prev_as[s])
            seat_fail_global_other[s] += max(0, cur_other - prev_other[s])
            seat_fail_global_unchecked[s] += max(0, cur_unchecked - prev_unchecked[s])

            prev_as[s] = cur_as
            prev_other[s] = cur_other
            prev_unchecked[s] = cur_unchecked

    old_hook = getattr(dg, "_DEBUG_ON_ATTEMPT_FAILURE_ATTRIBUTION", None)
    dg._DEBUG_ON_ATTEMPT_FAILURE_ATTRIBUTION = hook
    dg.MAX_BOARD_ATTEMPTS = MAX_ATTEMPTS
    
    success_boards = 0
    failed_boards = 0

    try:
        board_no = 1
        for r in range(RUNS):
            profile.hand_dealing_order = _rotate(["N", "E", "S", "W"], r)
            rng = random.Random(1000 + r)

            for _ in range(BOARDS_PER_RUN):
                try:
                    dg._build_single_constrained_deal(
                        rng=rng,
                        profile=profile,
                        board_number=board_no,
                        debug_board_stats=None,
                    )
                    success_boards += 1
                except dg.DealGenerationError:
                    failed_boards += 1
                finally:
                    board_no += 1
    finally:
        dg._DEBUG_ON_ATTEMPT_FAILURE_ATTRIBUTION = old_hook
        dg.MAX_BOARD_ATTEMPTS = old_max_attempts
        profile.hand_dealing_order = original_dealing_order

    # Print summary
    # Print summary
    total_as = sum(seat_fail_as_seat.values())
    total_other = sum(seat_fail_global_other.values())
    total_unchecked = sum(seat_fail_global_unchecked.values())

    print()
    print(f"Profile E: {PROFILE_E}")
    print()
    print(
        f"Boards: {RUNS*BOARDS_PER_RUN}   success={success_boards}   fail={failed_boards}   "
        f"attempt_fail_events={attempt_fail_events}"
    )
    print()
    print("bucket                         N       E       S       W     TOTAL")
    print("------------------------ -----------------------------------------")
    print(
        f"seat_fail_as_seat          {seat_fail_as_seat['N']:6d} {seat_fail_as_seat['E']:7d} "
        f"{seat_fail_as_seat['S']:7d} {seat_fail_as_seat['W']:7d} {total_as:9d}"
    )
    print(
        f"seat_fail_global_other     {seat_fail_global_other['N']:6d} {seat_fail_global_other['E']:7d} "
        f"{seat_fail_global_other['S']:7d} {seat_fail_global_other['W']:7d} {total_other:9d}"
    )
    print(
        f"seat_fail_global_unchecked {seat_fail_global_unchecked['N']:6d} {seat_fail_global_unchecked['E']:7d} "
        f"{seat_fail_global_unchecked['S']:7d} {seat_fail_global_unchecked['W']:7d} {total_unchecked:9d}"
    )
        # --- Helper-seat decision using local failure stats --------------------
    decision = _analyse_helper_seat_from_fail_stats(
        seat_fail_as_seat=seat_fail_as_seat,
        attempt_fail_events=attempt_fail_events,
        min_pain_share=0.25,      # "must matter" threshold
        dominance_factor=2.0,     # "twice as bad as the rest combined"
    )

    seats = ("N", "E", "S", "W")

    print()
    print("Helper-seat decision (local failure stats):")
    print(
        f"  mode={decision['mode']}  "
        f"helper_seat={decision['helper_seat']}  "
        f"seat_star={decision['seat_star']}  "
        f"p_star={decision['p_star']:.3f}  "
        f"reason={decision['reason']}"
    )
    print()
    print("Per-seat pain share (fraction of first-failure attempts):")
    for s in seats:
        ps = decision["pain_share"][s]
        print(f"  {s}: {ps:0.4f}")
    print()

    # For Profile E we *expect* North to be the obvious bottleneck helper seat.
    assert decision["mode"] == "helper"
    assert decision["helper_seat"] == "N"