from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pytest

from bridge_engine import deal_generator


@dataclass
class _DummyProfile:
    is_invariants_safety_profile: bool = False
    disable_constructive_help: bool = False
    # Optional opt-in for non-standard v2.
    enable_nonstandard_constructive_v2: Optional[bool] = None


def _modes_for(
    monkeypatch: pytest.MonkeyPatch,
    *,
    profile: _DummyProfile,
    enable_standard_flag: bool,
    enable_nonstandard_flag: bool,
):
    """
    Helper: patch global flags and call _get_constructive_mode(profile).
    """
    monkeypatch.setattr(
        deal_generator,
        "ENABLE_CONSTRUCTIVE_HELP",
        enable_standard_flag,
        raising=False,
    )
    monkeypatch.setattr(
        deal_generator,
        "ENABLE_CONSTRUCTIVE_HELP_NONSTANDARD",
        enable_nonstandard_flag,
        raising=False,
    )
    return deal_generator._get_constructive_mode(profile)  # type: ignore[attr-defined]


def test_constructive_mode_invariants_safety_disables_all(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = _DummyProfile(is_invariants_safety_profile=True)

    modes = _modes_for(
        monkeypatch,
        profile=profile,
        enable_standard_flag=True,
        enable_nonstandard_flag=True,
    )

    assert modes["standard"] is False
    assert modes["nonstandard_v2"] is False


def test_constructive_mode_default_all_flags_off(monkeypatch: pytest.MonkeyPatch) -> None:
    profile = _DummyProfile()

    modes = _modes_for(
        monkeypatch,
        profile=profile,
        enable_standard_flag=False,
        enable_nonstandard_flag=False,
    )

    assert modes["standard"] is False
    assert modes["nonstandard_v2"] is False


def test_constructive_mode_standard_only_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    profile = _DummyProfile()

    modes = _modes_for(
        monkeypatch,
        profile=profile,
        enable_standard_flag=True,
        enable_nonstandard_flag=False,
    )

    # v1 constructive help on; v2 still off.
    assert modes["standard"] is True
    assert modes["nonstandard_v2"] is False


def test_constructive_mode_nonstandard_defaults_to_global_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # No explicit profile opt-in → mirror the global flags.
    profile = _DummyProfile(enable_nonstandard_constructive_v2=None)

    modes = _modes_for(
        monkeypatch,
        profile=profile,
        enable_standard_flag=True,
        enable_nonstandard_flag=True,
    )

    assert modes["standard"] is True
    assert modes["nonstandard_v2"] is True


def test_constructive_mode_nonstandard_respects_profile_opt_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Profile explicitly opts out of v2 even if global flag is on.
    profile = _DummyProfile(enable_nonstandard_constructive_v2=False)

    modes = _modes_for(
        monkeypatch,
        profile=profile,
        enable_standard_flag=True,
        enable_nonstandard_flag=True,
    )

    assert modes["standard"] is True
    assert modes["nonstandard_v2"] is False


def test_constructive_mode_nonstandard_requires_both_global_flags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Profile wants v2, but global non-standard flag is off → no v2.
    profile = _DummyProfile(enable_nonstandard_constructive_v2=True)

    modes = _modes_for(
        monkeypatch,
        profile=profile,
        enable_standard_flag=True,
        enable_nonstandard_flag=False,
    )

    assert modes["standard"] is True
    assert modes["nonstandard_v2"] is False