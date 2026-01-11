from types import SimpleNamespace

import pytest

import bridge_engine.deal_generator as dg


def _mk_profile(*, invariants: bool, opt_in: bool = True):
    # deal_generator._get_constructive_mode uses getattr for these fields, so a
    # lightweight namespace is sufficient (avoids relying on any test-only
    # profile factories that may move between modules).
    return SimpleNamespace(
        is_invariants_safety_profile=invariants,
        disable_constructive_help=False,
        enable_nonstandard_constructive_v2=opt_in,
    )


def test_nonstandard_v2_policy_hook_called_when_enabled(monkeypatch):
    if not hasattr(dg, "_nonstandard_constructive_v2_policy"):
        pytest.skip("v2 policy seam wrapper not present")

    # Arrange: enable global nonstandard flag + profile opt-in.
    monkeypatch.setattr(dg, "ENABLE_CONSTRUCTIVE_HELP", True)
    monkeypatch.setattr(dg, "ENABLE_CONSTRUCTIVE_HELP_NONSTANDARD", True)
    profile = _mk_profile(invariants=False, opt_in=True)

    calls = []

    def hook(profile, board_number, attempt_number):
        calls.append((board_number, attempt_number))
        return {}

    monkeypatch.setattr(dg, "_DEBUG_NONSTANDARD_CONSTRUCTIVE_V2_POLICY", hook, raising=False)

    mode = dg._get_constructive_mode(profile)
    assert mode["nonstandard_v2"] is True

    dg._nonstandard_constructive_v2_policy(profile=profile, board_number=1, attempt_number=1)
    assert calls, "Expected v2 policy hook to be called when v2 is enabled"


def test_nonstandard_v2_policy_hook_not_called_when_disabled(monkeypatch):
    if not hasattr(dg, "_nonstandard_constructive_v2_policy"):
        pytest.skip("v2 policy seam wrapper not present")

    monkeypatch.setattr(dg, "ENABLE_CONSTRUCTIVE_HELP", True)
    monkeypatch.setattr(dg, "ENABLE_CONSTRUCTIVE_HELP_NONSTANDARD", False)
    profile = _mk_profile(invariants=False, opt_in=True)

    calls = []

    def hook(profile, board_number, attempt_number):
        calls.append((board_number, attempt_number))
        return {}

    monkeypatch.setattr(dg, "_DEBUG_NONSTANDARD_CONSTRUCTIVE_V2_POLICY", hook, raising=False)

    mode = dg._get_constructive_mode(profile)
    assert mode["nonstandard_v2"] is False

    # Even if called directly, the wrapper must guard itself.
    dg._nonstandard_constructive_v2_policy(profile=profile, board_number=1, attempt_number=1)
    assert calls == [], "Hook must not be invoked when global nonstandard is disabled"


def test_invariants_safety_profile_never_calls_v2_policy(monkeypatch):
    if not hasattr(dg, "_nonstandard_constructive_v2_policy"):
        pytest.skip("v2 policy seam wrapper not present")

    monkeypatch.setattr(dg, "ENABLE_CONSTRUCTIVE_HELP", True)
    monkeypatch.setattr(dg, "ENABLE_CONSTRUCTIVE_HELP_NONSTANDARD", True)
    profile = _mk_profile(invariants=True, opt_in=True)

    calls = []

    def hook(profile, board_number, attempt_number):
        calls.append((board_number, attempt_number))
        return {}

    monkeypatch.setattr(dg, "_DEBUG_NONSTANDARD_CONSTRUCTIVE_V2_POLICY", hook, raising=False)

    mode = dg._get_constructive_mode(profile)
    assert mode["nonstandard_v2"] is False

    dg._nonstandard_constructive_v2_policy(profile=profile, board_number=1, attempt_number=1)
    assert calls == [], "Invariants-safety profiles must never invoke the v2 policy seam"


def test_nonstandard_v2_policy_hook_receives_rich_inputs(monkeypatch):
    """Piece 1: the v2 policy seam accepts the same rich inputs as the shadow probe.

    This is a wrapper-level test (not a full integration test); it ensures the
    wrapper forwards the shapes we expect and copies mappings defensively.
    """
    if not hasattr(dg, "_nonstandard_constructive_v2_policy"):
        pytest.skip("v2 policy seam wrapper not present")

    monkeypatch.setattr(dg, "ENABLE_CONSTRUCTIVE_HELP", True)
    monkeypatch.setattr(dg, "ENABLE_CONSTRUCTIVE_HELP_NONSTANDARD", True)
    profile = _mk_profile(invariants=False, opt_in=True)

    chosen_indices = {"N": 0}
    seat_fail_counts = {"N": 2}
    seat_seen_counts = {"N": 5}
    viability_summary = {"N": "borderline"}
    rs_bucket_snapshot = {"W": {"total_seen_attempts": 3, "buckets": {"S": {"seen_attempts": 3, "matched_attempts": 1}}}}

    seen = {}

    def hook(
        profile,
        board_number,
        attempt_number,
        chosen_indices_arg,
        seat_fail_counts_arg,
        seat_seen_counts_arg,
        viability_summary_arg,
        rs_bucket_snapshot_arg,
    ):
        seen["board_number"] = board_number
        seen["attempt_number"] = attempt_number
        seen["chosen_indices"] = chosen_indices_arg
        seen["seat_fail_counts"] = seat_fail_counts_arg
        seen["seat_seen_counts"] = seat_seen_counts_arg
        seen["viability_summary"] = viability_summary_arg
        seen["rs_bucket_snapshot"] = rs_bucket_snapshot_arg
        return {}

    monkeypatch.setattr(dg, "_DEBUG_NONSTANDARD_CONSTRUCTIVE_V2_POLICY", hook, raising=False)

    dg._nonstandard_constructive_v2_policy(
        profile=profile,
        board_number=7,
        attempt_number=11,
        chosen_indices=chosen_indices,
        seat_fail_counts=seat_fail_counts,
        seat_seen_counts=seat_seen_counts,
        viability_summary=viability_summary,
        rs_bucket_snapshot=rs_bucket_snapshot,
    )

    assert seen["board_number"] == 7
    assert seen["attempt_number"] == 11
    assert seen["chosen_indices"] == chosen_indices
    assert seen["seat_fail_counts"] == seat_fail_counts
    assert seen["seat_seen_counts"] == seat_seen_counts
    assert seen["viability_summary"] == viability_summary
    assert seen["rs_bucket_snapshot"] == rs_bucket_snapshot

    # Defensive copy: the wrapper should not pass through the same dict objects.
    assert seen["chosen_indices"] is not chosen_indices
    assert seen["seat_fail_counts"] is not seat_fail_counts
    assert seen["seat_seen_counts"] is not seat_seen_counts
    assert seen["viability_summary"] is not viability_summary
    assert seen["rs_bucket_snapshot"] is not rs_bucket_snapshot
