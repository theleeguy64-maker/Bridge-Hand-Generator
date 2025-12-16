from __future__ import annotations

from typing import List, Tuple

import builtins
import types

import pytest

from bridge_engine import profile_wizard


# ---------------------------------------------------------------------------
# _input_int behaviour
# ---------------------------------------------------------------------------


def test_input_int_shows_range_suffix_by_default(monkeypatch, capsys) -> None:
    """
    When show_range_suffix is left at default (True), the prompt should
    include the (>=min and <=max) suffix.
    """
    # Simulate user pressing Enter (accept default)
    inputs = iter([""])

    def fake_input(prompt: str = "") -> str:
        # Capture prompt for later inspection
        print(prompt, end="")
        return next(inputs)

    monkeypatch.setattr(builtins, "input", fake_input)

    result = profile_wizard._input_int(
        prompt="Test prompt",
        default=5,
        minimum=0,
        maximum=10,
    )
    assert result == 5

    captured = capsys.readouterr().out
    assert "(>=0 and <=10)" in captured


def test_input_int_hides_range_suffix_when_requested(monkeypatch, capsys) -> None:
    """
    When show_range_suffix=False, the prompt should NOT include the
    (>=min and <=max) suffix.
    """
    inputs = iter([""])

    def fake_input(prompt: str = "") -> str:
        print(prompt, end="")
        return next(inputs)

    monkeypatch.setattr(builtins, "input", fake_input)

    result = profile_wizard._input_int(
        prompt="Test prompt",
        default=5,
        minimum=0,
        maximum=10,
        show_range_suffix=False,
    )
    assert result == 5

    captured = capsys.readouterr().out
    assert "(>=0 and <=10)" not in captured


# ---------------------------------------------------------------------------
# _build_suit_range_for_prompt defaults / prompts
# ---------------------------------------------------------------------------


def test_build_suit_range_for_prompt_uses_0_6_cards_and_0_10_hcp(monkeypatch) -> None:
    """
    For a fresh SuitRange (no existing), defaults should be:
    - min_cards=0, max_cards=6
    - min_hcp=0,   max_hcp=10

    And HCP prompts should show (0–10), not (0–37).
    """
    calls: List[Tuple[str, int, int, int, bool]] = []

    def fake_input_int(
        prompt: str,
        default: int,
        minimum: int,
        maximum: int,
        show_range_suffix: bool = True,
    ) -> int:
        calls.append((prompt, default, minimum, maximum, show_range_suffix))
        # Always accept the default
        return default

    monkeypatch.setattr(profile_wizard, "_input_int", fake_input_int)

    # We don't care about the return value here; we just inspect calls
    sr = profile_wizard._build_suit_range_for_prompt("Spades")
    # sanity check: the returned SuitRange should reflect the defaults
    assert sr.min_cards == 0
    assert sr.max_cards == 6
    assert sr.min_hcp == 0
    assert sr.max_hcp == 10

    # We expect four calls: min_cards, max_cards, min_hcp, max_hcp
    assert len(calls) == 4

    # Unpack calls in order for clarity
    (p_min_cards, d_min_cards, min_cards_min, min_cards_max, s_min_cards) = calls[0]
    (p_max_cards, d_max_cards, max_cards_min, max_cards_max, s_max_cards) = calls[1]
    (p_min_hcp,   d_min_hcp,   min_hcp_min,   min_hcp_max,   s_min_hcp)   = calls[2]
    (p_max_hcp,   d_max_hcp,   max_hcp_min,   max_hcp_max,   s_max_hcp)   = calls[3]

    # Defaults
    assert d_min_cards == 0
    assert d_max_cards == 6
    assert d_min_hcp == 0
    assert d_max_hcp == 10

    # Ranges
    assert (min_cards_min, min_cards_max) == (0, 13)
    assert (max_cards_min, max_cards_max) == (0, 13)
    assert (min_hcp_min,   min_hcp_max)   == (0, 10)
    assert (max_hcp_min,   max_hcp_max)   == (0, 10)

    # Prompts
    assert "Min cards (0–13)" in p_min_cards
    assert "Max cards (0–13)" in p_max_cards
    assert "Min HCP (0–10)" in p_min_hcp
    assert "Max HCP (0–10)" in p_max_hcp

    # All calls should suppress the extra (>=.. <=..) suffix
    assert s_min_cards is False
    assert s_max_cards is False
    assert s_min_hcp is False
    assert s_max_hcp is False


# ---------------------------------------------------------------------------
# _build_standard_constraints uses no suffix for total HCP
# ---------------------------------------------------------------------------


def test_build_standard_constraints_hides_range_suffix_for_totals(monkeypatch) -> None:
    """
    The standard constraints prompts for total HCP should not show the
    (>=... and <=...) suffix. They should call _input_int with
    show_range_suffix=False.
    """
    calls: List[Tuple[str, int, int, int, bool]] = []

    def fake_input_int(
        prompt: str,
        default: int,
        minimum: int,
        maximum: int,
        show_range_suffix: bool = True,
    ) -> int:
        calls.append((prompt, default, minimum, maximum, show_range_suffix))
        return default

    monkeypatch.setattr(profile_wizard, "_input_int", fake_input_int)

    # We don't care about the returned StandardSuitConstraints, only about how
    # _input_int was called for total HCP.
    sc = profile_wizard._build_standard_constraints(existing=None)
    # sanity check: we got a StandardSuitConstraints back
    from bridge_engine.hand_profile import StandardSuitConstraints as SSC
    assert isinstance(sc, SSC)

    # The first two calls should be total_min_hcp and total_max_hcp
    assert len(calls) >= 2
    (p_min, d_min, min_min, min_max, s_min) = calls[0]
    (p_max, d_max, max_min, max_max, s_max) = calls[1]

    assert "Total min HCP (0–37)" in p_min
    assert "Total max HCP (0–37)" in p_max
    assert (min_min, min_max) == (0, 37)
    assert (max_min, max_max) == (0, 37)

    # And both should have show_range_suffix=False
    assert s_min is False
    assert s_max is False