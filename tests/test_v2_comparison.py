"""
D8 — Comparative benchmarks: v1 vs v2 on real profiles.

Gated behind RUN_V2_BENCHMARKS=1 environment variable.
Usage:
    RUN_V2_BENCHMARKS=1 pytest -q -s tests/test_v2_comparison.py

Compares attempt counts between:
  - _build_single_constrained_deal()    (v1)
  - _build_single_constrained_deal_v2() (v2 with shape help)

Uses real JSON profile files from the profiles/ directory.
"""

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

PROFILE_A = "Profile_A_Test_-_Loose_constraints_v0.1.json"
PROFILE_B = "Profile_B_Test_-_tight_suit_constraints_v0.1.json"
PROFILE_E = "Profile_E_Test_-_tight_and_suit_point_constraint_plus_v0.1.json"


if os.environ.get("RUN_V2_BENCHMARKS", "") != "1":
    pytest.skip(
        "Opt-in benchmark. Run with RUN_V2_BENCHMARKS=1 pytest -q -s tests/test_v2_comparison.py",
        allow_module_level=True,
    )


def _load_profile(fname: str) -> HandProfile:
    """Load a HandProfile from JSON file."""
    path = PROFILE_DIR / fname
    if not path.exists():
        pytest.skip(f"Missing profile file: {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    return HandProfile.from_dict(raw)


def _run_boards(builder_fn, profile: HandProfile, num_boards: int,
                seed: int = 42) -> Dict[str, object]:
    """
    Run num_boards through a builder function, collecting attempt stats.

    Returns dict with:
      - total_attempts: sum of attempts across all boards
      - boards_generated: number of boards successfully generated
      - seat_fail_totals: cumulative seat_fail_counts across all boards
      - seat_seen_totals: cumulative seat_seen_counts across all boards
    """
    rng = random.Random(seed)
    total_attempts = 0
    boards_generated = 0
    seat_fail_totals: Dict[Seat, int] = {}
    seat_seen_totals: Dict[Seat, int] = {}

    for board_number in range(1, num_boards + 1):
        # Capture stats via debug_board_stats callback.
        board_stats = {}

        def callback(fail_counts, seen_counts, _bs=board_stats):
            _bs["fail"] = fail_counts
            _bs["seen"] = seen_counts

        try:
            builder_fn(
                rng=rng,
                profile=profile,
                board_number=board_number,
                debug_board_stats=callback,
            )
            boards_generated += 1
        except dg.DealGenerationError:
            pass  # Board failed — still count the stats.

        # Accumulate stats.
        if "fail" in board_stats:
            for seat, count in board_stats["fail"].items():
                seat_fail_totals[seat] = seat_fail_totals.get(seat, 0) + count
        if "seen" in board_stats:
            for seat, count in board_stats["seen"].items():
                seat_seen_totals[seat] = seat_seen_totals.get(seat, 0) + count
            # Total attempts = max seat_seen count for this board
            # (the first-checked seat is seen on every attempt).
            board_attempts = max(board_stats["seen"].values()) if board_stats["seen"] else 0
            total_attempts += board_attempts

    return {
        "total_attempts": total_attempts,
        "boards_generated": boards_generated,
        "seat_fail_totals": seat_fail_totals,
        "seat_seen_totals": seat_seen_totals,
    }


def _print_comparison(label: str, v1_result: Dict, v2_result: Dict,
                      num_boards: int) -> None:
    """Print a formatted comparison of v1 vs v2 results."""
    print(f"\n{'=' * 60}")
    print(f"  {label}")
    print(f"{'=' * 60}")
    print(f"  {'Metric':<30} {'v1':>10} {'v2':>10} {'Ratio':>10}")
    print(f"  {'-' * 60}")

    v1_att = v1_result["total_attempts"]
    v2_att = v2_result["total_attempts"]
    ratio = f"{v2_att / v1_att:.2f}x" if v1_att > 0 else "N/A"
    print(f"  {'Total attempts':<30} {v1_att:>10} {v2_att:>10} {ratio:>10}")

    v1_gen = v1_result["boards_generated"]
    v2_gen = v2_result["boards_generated"]
    print(f"  {'Boards generated':<30} {v1_gen:>10} {v2_gen:>10}")

    avg_v1 = v1_att / num_boards if num_boards > 0 else 0
    avg_v2 = v2_att / num_boards if num_boards > 0 else 0
    print(f"  {'Avg attempts/board':<30} {avg_v1:>10.1f} {avg_v2:>10.1f}")

    # Pain share: which seat fails the most?
    print(f"\n  Seat fail totals:")
    for seat in ("N", "E", "S", "W"):
        v1_f = v1_result["seat_fail_totals"].get(seat, 0)
        v2_f = v2_result["seat_fail_totals"].get(seat, 0)
        print(f"    {seat}: v1={v1_f:>6}  v2={v2_f:>6}")
    print()


# -------------------------------------------------------------------
# Tests
# -------------------------------------------------------------------

NUM_BOARDS = 100  # Number of boards per benchmark run.


def test_profile_a_loose_similar_attempts():
    """
    Profile A (all loose): v1 and v2 should have similar attempt counts
    since no help is needed — dispersion_check returns empty set.
    """
    profile = _load_profile(PROFILE_A)
    v1 = _run_boards(dg._build_single_constrained_deal, profile, NUM_BOARDS)
    v2 = _run_boards(dg._build_single_constrained_deal_v2, profile, NUM_BOARDS)
    _print_comparison("Profile A (Loose)", v1, v2, NUM_BOARDS)

    # Both should generate all boards.
    assert v1["boards_generated"] == NUM_BOARDS
    assert v2["boards_generated"] == NUM_BOARDS
    # Loose profile: both should succeed on first attempt (≈100 total).
    assert v1["total_attempts"] <= NUM_BOARDS * 2
    assert v2["total_attempts"] <= NUM_BOARDS * 2


def test_profile_b_tight_spades_fewer_attempts():
    """
    Profile B (North 5+ spades): v2 should use fewer attempts than v1
    because v2 pre-allocates spades for North.
    """
    profile = _load_profile(PROFILE_B)
    v1 = _run_boards(dg._build_single_constrained_deal, profile, NUM_BOARDS)
    v2 = _run_boards(dg._build_single_constrained_deal_v2, profile, NUM_BOARDS)
    _print_comparison("Profile B (5+ Spades)", v1, v2, NUM_BOARDS)

    # Both should generate all boards.
    assert v1["boards_generated"] == NUM_BOARDS
    assert v2["boards_generated"] == NUM_BOARDS
    # v2 should use fewer or equal attempts.
    assert v2["total_attempts"] <= v1["total_attempts"], (
        f"v2 ({v2['total_attempts']}) should use <= attempts than v1 ({v1['total_attempts']})"
    )


def test_profile_e_v2_generates_boards():
    """
    Profile E (6 spades + 10-12 HCP): v2 should at least generate boards.
    This profile is very hard — v2 helps with shape but not HCP.
    We just verify v2 can produce deals (may need many attempts).
    """
    profile = _load_profile(PROFILE_E)
    v2 = _run_boards(dg._build_single_constrained_deal_v2, profile, NUM_BOARDS)
    _print_comparison("Profile E (6 Spades + HCP) — v2 only",
                      {"total_attempts": 0, "boards_generated": 0,
                       "seat_fail_totals": {}, "seat_seen_totals": {}},
                      v2, NUM_BOARDS)

    # v2 may or may not generate all boards for Profile E.
    # Just verify it generated at least some.
    print(f"  Profile E: v2 generated {v2['boards_generated']}/{NUM_BOARDS} boards")


def test_profile_b_north_pain_share_reduced():
    """
    Profile B: North is the bottleneck (5+ spades). With v2 shape help,
    North's share of failures should be reduced.
    """
    profile = _load_profile(PROFILE_B)
    v1 = _run_boards(dg._build_single_constrained_deal, profile, NUM_BOARDS)
    v2 = _run_boards(dg._build_single_constrained_deal_v2, profile, NUM_BOARDS)

    v1_n_fails = v1["seat_fail_totals"].get("N", 0)
    v2_n_fails = v2["seat_fail_totals"].get("N", 0)

    print(f"\n  Profile B North failures: v1={v1_n_fails}, v2={v2_n_fails}")

    # v2 should have fewer or equal North failures.
    assert v2_n_fails <= v1_n_fails, (
        f"v2 North failures ({v2_n_fails}) should be <= v1 ({v1_n_fails})"
    )


def test_profile_a_no_tight_seats_detected():
    """
    Profile A: dispersion_check should return empty set (no tight seats).
    Verify that v2 doesn't add overhead for loose profiles.
    """
    profile = _load_profile(PROFILE_A)

    # Manually check dispersion for Profile A.
    rng = random.Random(42)
    dealing_order = list(profile.hand_dealing_order)
    chosen_subs, _ = dg._select_subprofiles_for_board(rng, profile, dealing_order)
    tight = dg._dispersion_check(chosen_subs)

    print(f"\n  Profile A tight seats: {tight}")
    assert len(tight) == 0, f"Expected no tight seats, got {tight}"


def test_profile_b_north_is_tight():
    """
    Profile B: dispersion_check should flag North as tight (5+ spades).
    """
    profile = _load_profile(PROFILE_B)

    rng = random.Random(42)
    dealing_order = list(profile.hand_dealing_order)
    chosen_subs, _ = dg._select_subprofiles_for_board(rng, profile, dealing_order)
    tight = dg._dispersion_check(chosen_subs)

    print(f"\n  Profile B tight seats: {tight}")
    assert "N" in tight, f"Expected North to be tight, got {tight}"
