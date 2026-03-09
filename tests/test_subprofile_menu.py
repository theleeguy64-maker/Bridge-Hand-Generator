# tests/test_subprofile_menu.py
"""
Tests for the constraint type gate menu in wizard_flow._build_subprofile.

Covers the gate menu choices:
  0) Exit — skip both standard and extra, return defaults/existing
  1) Standard — run _build_standard_constraints, then fall through to extra menu
  2) Non-Standard — skip standard, jump to extra constraint menu
"""

from __future__ import annotations

from bridge_engine.hand_profile import (
    RandomSuitConstraintData,
    StandardSuitConstraints,
    SubProfile,
    SuitRange,
)
from bridge_engine import profile_wizard
from bridge_engine import wizard_flow
from bridge_engine import wizard_io as wiz_io


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_standard(hcp_min: int = 0, hcp_max: int = 37) -> StandardSuitConstraints:
    """Build a StandardSuitConstraints with custom HCP bounds."""
    return StandardSuitConstraints(
        SuitRange(),
        SuitRange(),
        SuitRange(),
        SuitRange(),
        total_min_hcp=hcp_min,
        total_max_hcp=hcp_max,
    )


def _patch_io(monkeypatch, prompts, ints):
    """Patch wiz_io.prompt_str and profile_wizard._input_int with iterators."""
    monkeypatch.setattr(wiz_io, "prompt_str", lambda prompt, default="": next(prompts))
    monkeypatch.setattr(profile_wizard, "_input_int", lambda prompt, **kw: next(ints))


# ---------------------------------------------------------------------------
# Gate choice 0 — Exit: skip everything, return defaults
# ---------------------------------------------------------------------------


def test_gate_exit_new_subprofile(monkeypatch):
    """Choice 0 on a new subprofile returns wide-open defaults, no extras."""
    _patch_io(monkeypatch, iter([""]), iter([0]))

    result = wizard_flow._build_subprofile("N")

    assert isinstance(result, SubProfile)
    # Standard should be wide-open defaults
    assert result.standard.total_min_hcp == 0
    assert result.standard.total_max_hcp == 37
    # No extra constraints
    assert result.random_suit_constraint is None
    assert result.partner_contingent_constraint is None
    assert result.opponents_contingent_suit_constraint is None
    assert result.name is None


def test_gate_exit_preserves_existing(monkeypatch):
    """Choice 0 with an existing subprofile preserves its values."""
    existing = SubProfile(
        standard=_make_standard(10, 15),
        name="Opener",
        weight_percent=40.0,
    )

    _patch_io(monkeypatch, iter([""]), iter([0]))

    result = wizard_flow._build_subprofile("N", existing=existing)

    assert result.standard.total_min_hcp == 10
    assert result.standard.total_max_hcp == 15
    assert result.name == "Opener"
    assert result.weight_percent == 40.0


# ---------------------------------------------------------------------------
# Gate choice 1 — Standard: runs builder, then extra constraint menu
# ---------------------------------------------------------------------------


def test_gate_standard_runs_builder(monkeypatch):
    """Choice 1 runs _build_standard_constraints, then reaches extra menu."""
    # Stub _build_standard_constraints to avoid its many prompts
    custom_std = _make_standard(12, 20)
    monkeypatch.setattr(
        wizard_flow,
        "_build_standard_constraints",
        lambda existing=None, label_suffix="": custom_std,
    )

    # prompt_str → "Test" (name), ints → gate=1, extra=1(None)
    _patch_io(monkeypatch, iter(["Test"]), iter([1, 1]))

    result = wizard_flow._build_subprofile("S")

    assert result.name == "Test"
    assert result.standard.total_min_hcp == 12
    assert result.standard.total_max_hcp == 20
    # Extra = None (choice 1)
    assert result.random_suit_constraint is None
    assert result.partner_contingent_constraint is None
    assert result.opponents_contingent_suit_constraint is None


# ---------------------------------------------------------------------------
# Gate choice 2 — Non-Standard: skip standard, reach extra constraint menu
# ---------------------------------------------------------------------------


def test_gate_nonstandard_skips_standard(monkeypatch):
    """Choice 2 skips standard constraints and jumps to extra menu."""
    # Ensure _build_standard_constraints is NOT called
    build_called = []

    def spy_build(*args, **kwargs):
        build_called.append(True)
        return _make_standard()

    monkeypatch.setattr(wizard_flow, "_build_standard_constraints", spy_build)

    # ints → gate=2, extra=1(None)
    _patch_io(monkeypatch, iter([""]), iter([2, 1]))

    result = wizard_flow._build_subprofile("E")

    # Standard builder should NOT have been called
    assert build_called == []
    # Standard should be wide-open defaults
    assert result.standard.total_min_hcp == 0
    assert result.standard.total_max_hcp == 37


def test_gate_nonstandard_reaches_extra_menu(monkeypatch):
    """Choice 2 reaches the extra constraint menu (choice 2 = RS)."""
    # Stub the RS builder to avoid its prompts
    fake_rs = RandomSuitConstraintData(
        allowed_suits=["S", "H", "D", "C"],
        required_suits_count=1,
        suit_ranges={"S": SuitRange(min_cards=4, max_cards=8)},
        pair_overrides=[],
    )
    monkeypatch.setattr(
        wizard_flow,
        "_build_random_suit_constraint",
        lambda existing=None: fake_rs,
    )

    # ints → gate=2, extra=2(RS)
    _patch_io(monkeypatch, iter([""]), iter([2, 2]))

    result = wizard_flow._build_subprofile("W")

    assert result.random_suit_constraint is fake_rs
    # Standard untouched (wide-open)
    assert result.standard.total_min_hcp == 0
