#!/usr/bin/env python3
"""
Benchmark Portfolio — 5 profiles spanning trivial to hardest.

Usage:
    .venv/bin/python benchmark_portfolio.py [num_boards]

Default: 20 boards per profile. Outputs per-profile timing stats.
"""

import json
import random
import statistics
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from bridge_engine.hand_profile import HandProfile
from bridge_engine.deal_generator import generate_deals
from bridge_engine.setup_env import run_setup

# ---------------------------------------------------------------------------
# Benchmark portfolio: 5 profiles (trivial → hardest)
# ---------------------------------------------------------------------------
BENCHMARK_PROFILES = [
    ("Profile A (Loose)",       "Profile_A_Test_-_Loose_constraints_v0.1.json"),
    ("Profile D (Suit+Pts)",    "Profile_D_Test_-_tight_and_suit_point_constraint_v0.1.json"),
    ("Profile E (Suit+Pts+)",   "Profile_E_Test_-_tight_and_suit_point_constraint_plus_v0.1.json"),
    ("Our 1 Major & Interf.",   "Our_1_Major_&_Opponents_Interference_v0.2.json"),
    ("Defense to 3 Weak 2s",    "Defense_to_3_Weak_2s_-_Multi__Overcall_Shapes_v0.3.json"),
]

PROFILE_DIR = Path(__file__).resolve().parent / "profiles"
SEED = 778899  # Canonical deterministic seed


def load_profile(filename: str) -> HandProfile:
    path = PROFILE_DIR / filename
    raw = json.loads(path.read_text(encoding="utf-8"))
    return HandProfile.from_dict(raw)


def run_benchmark(num_boards: int = 20) -> list[dict]:
    """Run all 5 profiles and collect timing data."""
    import tempfile

    results = []

    for label, filename in BENCHMARK_PROFILES:
        profile = load_profile(filename)

        # Create a minimal setup (temp dir for output files we won't use)
        with tempfile.TemporaryDirectory() as tmp:
            setup = run_setup(
                base_dir=Path(tmp),
                owner="Benchmark",
                profile_name=label,
                ask_seed_choice=False,
                use_seeded_default=True,
            )

            # Time the full generation
            t0 = time.monotonic()
            deal_set = generate_deals(
                setup, profile, num_boards, enable_rotation=False,
            )
            wall_time = time.monotonic() - t0

        board_times = deal_set.board_times
        result = {
            "label": label,
            "boards": len(deal_set.deals),
            "wall_time": wall_time,
            "reseeds": deal_set.reseed_count,
            "avg_ms": statistics.mean(board_times) * 1000 if board_times else 0,
            "median_ms": statistics.median(board_times) * 1000 if board_times else 0,
            "max_ms": max(board_times) * 1000 if board_times else 0,
            "min_ms": min(board_times) * 1000 if board_times else 0,
            "p95_ms": (
                sorted(board_times)[int(len(board_times) * 0.95)] * 1000
                if len(board_times) >= 5
                else max(board_times) * 1000 if board_times else 0
            ),
        }
        results.append(result)

    return results


def print_results(results: list[dict], num_boards: int) -> None:
    """Print benchmark results as a formatted table."""
    print(f"\n{'='*90}")
    print(f"  BENCHMARK PORTFOLIO — {num_boards} boards/profile, seed={SEED}")
    print(f"{'='*90}")
    print(
        f"  {'Profile':<28} {'Boards':>6} {'Wall(s)':>8} "
        f"{'Avg(ms)':>8} {'Med(ms)':>8} {'P95(ms)':>8} {'Max(ms)':>8} {'Reseed':>6}"
    )
    print(f"  {'-'*28} {'-'*6} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*6}")

    for r in results:
        print(
            f"  {r['label']:<28} {r['boards']:>6} {r['wall_time']:>8.3f} "
            f"{r['avg_ms']:>8.1f} {r['median_ms']:>8.1f} {r['p95_ms']:>8.1f} "
            f"{r['max_ms']:>8.1f} {r['reseeds']:>6}"
        )

    total_wall = sum(r["wall_time"] for r in results)
    total_boards = sum(r["boards"] for r in results)
    print(f"  {'-'*28} {'-'*6} {'-'*8}")
    print(f"  {'TOTAL':<28} {total_boards:>6} {total_wall:>8.3f}")
    print(f"{'='*90}\n")


if __name__ == "__main__":
    num_boards = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    print(f"Running benchmark: {num_boards} boards per profile...")

    results = run_benchmark(num_boards)
    print_results(results, num_boards)
