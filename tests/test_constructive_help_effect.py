import random
from typing import List

import pytest

from bridge_engine import deal_generator
from bridge_engine.setup_env import run_setup


class _DummyProfile:
    """
    Minimal profile object that drives the *fallback* deal_generator path.

    We deliberately avoid HandProfile here so that:

      - generate_deals(...) uses the simple random-deal path,
      - profile evolution cannot accidentally break anything,
      - these tests stay stable even as HandProfile evolves.

    The fallback path only needs:
      - dealer
      - hand_dealing_order
    """

    dealer: str = "N"
    hand_dealing_order: List[str] = ["N", "E", "S", "W"]


def _make_setup(tmp_path) -> deal_generator.SetupResult:
    """
    Use the real setup helper so we're exercising the true CLI/setup
    pipeline, but with a dummy profile name (since we pass our own
    profile object into generate_deals).
    """
    return run_setup(
        base_dir=tmp_path,
        owner="TestOwner",
        profile_name="Dummy profile for constructive help tests",
        ask_seed_choice=False,
        use_seeded_default=True,
    )


def test_constructive_help_harness_builds_deals(tmp_path: pytest.TempPathFactory) -> None:
    """
    Basic sanity: generate_deals(...) with a non-HandProfile object
    should successfully produce a small set of deals using the fallback
    (simple random-deal) path.
    """
    setup = _make_setup(tmp_path)
    profile = _DummyProfile()

    deal_set = deal_generator.generate_deals(
        setup=setup,
        profile=profile,
        num_deals=8,
    )
    assert len(deal_set.deals) == 8


def test_viability_summary_matches_classify_viability() -> None:
    """
    Smoke test for the diagnostic viability summary helper.

    It should:
      * compute attempts / successes / failures / success_rate correctly, and
      * use classify_viability() for the 'viability' label.
    """
    seat_fail_counts = {"N": 0, "E": 8}
    seat_seen_counts = {"N": 10, "E": 8}

    summary = deal_generator._compute_viability_summary(
        seat_fail_counts=seat_fail_counts,
        seat_seen_counts=seat_seen_counts,
    )

    # North: 10 attempts, 0 failures -> 10 successes, 100% success
    n_stats = summary["N"]
    assert n_stats["attempts"] == 10
    assert n_stats["failures"] == 0
    assert n_stats["successes"] == 10
    assert n_stats["success_rate"] == 1.0
    assert n_stats["viability"] == deal_generator.classify_viability(10, 10)

    # East: 8 attempts, 8 failures -> 0 successes, 0% success
    e_stats = summary["E"]
    assert e_stats["attempts"] == 8
    assert e_stats["failures"] == 8
    assert e_stats["successes"] == 0
    assert e_stats["success_rate"] == 0.0
    assert e_stats["viability"] == deal_generator.classify_viability(0, 8)
