# test_deal_generator_debug_hook.py

import random
from typing import Dict, List

import pytest

from bridge_engine import deal_generator


class DummySubprofile:
    """Minimal subprofile stub with optional 'non-standard' constraint marker."""

    def __init__(self, has_nonstandard: bool = False) -> None:
        if has_nonstandard:
            # Trigger the has_nonstandard logic in deal_generator._build_single_constrained_deal
            self.random_suit_constraint = object()


class DummySeatProfile:
    """Minimal seat profile with a configurable number of subprofiles."""

    def __init__(self, num_subprofiles: int = 1, has_nonstandard: bool = False) -> None:
        self.subprofiles = [
            DummySubprofile(has_nonstandard=has_nonstandard)
            for _ in range(num_subprofiles)
        ]


class DummyProfile:
    """
    Minimal duck-typed profile for exercising _build_single_constrained_deal.

    We deliberately:
      - provide a seat_profiles mapping with DummySeatProfiles
      - disable NS index coupling (so ns_driver_seat is never consulted)
      - control the invariants fast-path via is_invariants_safety_profile
      - control has_nonstandard via nonstandard_seats
    """

    def __init__(
        self,
        invariants_safety: bool = False,
        nonstandard_seats: List[str] | None = None,
    ) -> None:
        if nonstandard_seats is None:
            nonstandard_seats = []

        self.profile_name = "Dummy profile"
        self.dealer = "N"
        self.hand_dealing_order = ["N", "E", "S", "W"]

        self.seat_profiles: Dict[str, DummySeatProfile] = {}
        for seat in ["N", "E", "S", "W"]:
            self.seat_profiles[seat] = DummySeatProfile(
                num_subprofiles=1,
                has_nonstandard=seat in nonstandard_seats,
            )

        # Ensure NS coupling never triggers (so ns_driver_seat is not needed)
        self.ns_index_coupling_enabled = False

        # Opt in/out of the invariants fast path.
        self.is_invariants_safety_profile = invariants_safety


def test_debug_hook_called_when_max_attempts_exhausted(monkeypatch) -> None:
    """
    When MAX_BOARD_ATTEMPTS is exhausted for a profile with non-standard
    constraints (no invariants fast-path), the debug hook should be invoked
    with diagnostics and we should raise DealGenerationError.
    """
    # Non-safety profile, with non-standard constraints on at least one seat.
    profile = DummyProfile(invariants_safety=False, nonstandard_seats=["N"])

    # Make deal_generator treat DummySeatProfile as its SeatProfile type.
    monkeypatch.setattr(deal_generator, "SeatProfile", DummySeatProfile)

    # Force every seat match to fail so we always exhaust attempts.
    def always_fail_match(*args, **kwargs):
        # Signature: _match_seat(...)->(matched, chosen_random_suit, fail_reason)
        return False, None, "other"

    monkeypatch.setattr(deal_generator, "_match_seat", always_fail_match)
    monkeypatch.setattr(deal_generator, "MAX_BOARD_ATTEMPTS", 3)

    captured: Dict[str, object] = {}

    def debug_hook(
        profile_arg,
        board_number,
        attempts,
        chosen_indices,
        seat_fail_counts,
        viability_summary,  # new param
    ):
        captured["profile_name"] = getattr(profile_arg, "profile_name", "")
        captured["board_number"] = board_number
        captured["attempts"] = attempts
        captured["chosen_indices"] = dict(chosen_indices)
        captured["seat_fail_counts"] = dict(seat_fail_counts)
        captured["viability_summary"] = viability_summary

    deal_generator._DEBUG_ON_MAX_ATTEMPTS = debug_hook  # type: ignore[attr-defined]

    rng = random.Random(1234)
    with pytest.raises(deal_generator.DealGenerationError):
        deal_generator._build_single_constrained_deal(
            rng=rng,
            profile=profile,
            board_number=1,
        )

    # Clean up to avoid leaking the hook into other tests
    deal_generator._DEBUG_ON_MAX_ATTEMPTS = None  # type: ignore[attr-defined]

    # Sanity checks on what the hook saw.
    assert captured["profile_name"] == "Dummy profile"
    assert captured["board_number"] == 1
    assert captured["attempts"] == 3
    # There should be at least one seat recorded as failing.
    assert captured["seat_fail_counts"]
    # And we should have at least some index snapshot.
    assert isinstance(captured["chosen_indices"], dict)

    # Viability summary should be a dict keyed by seat, matching the fail-count keys.
    assert isinstance(captured["viability_summary"], dict)
    assert set(captured["viability_summary"].keys()) == set(
        captured["seat_fail_counts"].keys()
    )


def test_debug_hook_not_called_for_invariants_fast_path(monkeypatch) -> None:
    """
    For invariants-safety profiles (is_invariants_safety_profile=True) with only
    standard constraints, the fast path should return a deal without ever
    calling the debug hook.
    """
    # Safety profile, no non-standard constraints.
    profile = DummyProfile(invariants_safety=True, nonstandard_seats=[])

    # Make deal_generator treat DummySeatProfile as its SeatProfile type.
    monkeypatch.setattr(deal_generator, "SeatProfile", DummySeatProfile)

    calls: List[int] = []

    def debug_hook(*args, **kwargs):
        calls.append(1)

    deal_generator._DEBUG_ON_MAX_ATTEMPTS = debug_hook  # type: ignore[attr-defined]

    rng = random.Random(5678)
    # This should succeed quickly via the invariants fast path.
    deal = deal_generator._build_single_constrained_deal(
        rng=rng,
        profile=profile,
        board_number=1,
    )

    deal_generator._DEBUG_ON_MAX_ATTEMPTS = None  # type: ignore[attr-defined]

    # Ensure we actually produced something and never called the hook.
    assert deal is not None
    assert calls == []