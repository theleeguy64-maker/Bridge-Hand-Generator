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
      - constructive-help toggling cannot accidentally break anything,
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
    Basic sanity: with constructive help *disabled*, generate_deals(...)
    should successfully produce a small set of deals using the fallback
    (non-HandProfile) path.
    """
    setup = _make_setup(tmp_path)
    profile = _DummyProfile()

    # Ensure the global flag is definitely off for this sanity test.
    old_flag = deal_generator.ENABLE_CONSTRUCTIVE_HELP
    deal_generator.ENABLE_CONSTRUCTIVE_HELP = False
    try:
        deal_set = deal_generator.generate_deals(
            setup=setup,
            profile=profile,
            num_deals=8,
        )
        assert len(deal_set.deals) == 8
    finally:
        deal_generator.ENABLE_CONSTRUCTIVE_HELP = old_flag


def test_constructive_help_does_not_increase_failures_for_hard_seat(
    tmp_path: pytest.TempPathFactory,
) -> None:
    """
    For v1, we don't try to *prove* constructive help improves anything;
    we only assert that toggling the flag from False->True does not make
    things worse for the simple fallback-profile path:

      - Both runs produce the requested number of deals.
      - No DealGenerationError is raised in either mode.

    Later, once we have a stable "hard" standard-only profile and
    diagnostics, we can tighten this into a true comparative test.
    """
    setup = _make_setup(tmp_path)
    profile = _DummyProfile()

    old_flag = deal_generator.ENABLE_CONSTRUCTIVE_HELP

    try:
        # Baseline: help disabled
        deal_generator.ENABLE_CONSTRUCTIVE_HELP = False
        baseline_set = deal_generator.generate_deals(
            setup=setup,
            profile=profile,
            num_deals=12,
        )

        # Experimental: help enabled
        deal_generator.ENABLE_CONSTRUCTIVE_HELP = True
        helped_set = deal_generator.generate_deals(
            setup=setup,
            profile=profile,
            num_deals=12,
        )

        assert len(baseline_set.deals) == 12
        assert len(helped_set.deals) == 12

    finally:
        deal_generator.ENABLE_CONSTRUCTIVE_HELP = old_flag
        
        
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
    