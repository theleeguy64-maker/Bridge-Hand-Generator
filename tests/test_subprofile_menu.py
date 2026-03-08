# tests/test_subprofile_menu.py
"""
Tests for the menu-driven _build_subprofile() and _format_standard_constraints_summary().

Tests monkeypatch at the wizard_flow level to control interactive inputs.
"""

from __future__ import annotations

from typing import Optional

import pytest

from bridge_engine.hand_profile_model import (
    StandardSuitConstraints,
    SubProfile,
    SuitRange,
    RandomSuitConstraintData,
    PartnerContingentData,
    OpponentContingentSuitData,
)
from bridge_engine import wizard_flow


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _wide_open_standard() -> StandardSuitConstraints:
    """Return wide-open standard constraints (all defaults)."""
    return StandardSuitConstraints(
        spades=SuitRange(),
        hearts=SuitRange(),
        diamonds=SuitRange(),
        clubs=SuitRange(),
    )


def _constrained_standard() -> StandardSuitConstraints:
    """Return a constrained standard for testing."""
    return StandardSuitConstraints(
        total_min_hcp=10,
        total_max_hcp=15,
        spades=SuitRange(min_cards=5, max_cards=7, min_hcp=0, max_hcp=10),
        hearts=SuitRange(min_cards=2, max_cards=5, min_hcp=0, max_hcp=10),
        diamonds=SuitRange(),
        clubs=SuitRange(),
    )


def _dummy_rs() -> RandomSuitConstraintData:
    return RandomSuitConstraintData(
        allowed_suits=["S", "H", "D", "C"],
        required_suits_count=1,
        suit_ranges=[SuitRange(min_cards=5, max_cards=7)],
        pair_overrides=[],
    )


def _dummy_pc() -> PartnerContingentData:
    return PartnerContingentData(
        partner_seat="S",
        suit_range=SuitRange(min_cards=3, max_cards=5),
    )


def _dummy_oc() -> OpponentContingentSuitData:
    return OpponentContingentSuitData(
        opponent_seat="E",
        suit_range=SuitRange(min_cards=3, max_cards=5),
    )


# ---------------------------------------------------------------------------
# _format_standard_constraints_summary
# ---------------------------------------------------------------------------


class TestFormatStandardConstraintsSummary:
    """Tests for _format_standard_constraints_summary()."""

    def test_wide_open(self) -> None:
        std = _wide_open_standard()
        result = wizard_flow._format_standard_constraints_summary(std)
        assert "wide open" in result
        assert "no restrictions" in result

    def test_constrained(self) -> None:
        std = _constrained_standard()
        result = wizard_flow._format_standard_constraints_summary(std)
        assert "HCP: 10-15" in result
        assert "S: 5-7 cards" in result
        assert "H: 2-5 cards" in result
        # Wide-open suits still shown with full ranges
        assert "D: 0-13 cards" in result
        assert "C: 0-13 cards" in result


# ---------------------------------------------------------------------------
# _build_subprofile menu-driven tests
# ---------------------------------------------------------------------------


class TestBuildSubprofileMenu:
    """Tests for the menu-driven _build_subprofile()."""

    def _patch_basics(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Patch prompt_str to return empty (skip name)."""
        monkeypatch.setattr(wizard_flow.wiz_io, "prompt_str", lambda prompt: "")

    def test_exit_immediately_returns_wide_open(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Choosing 0 (Exit) immediately returns wide-open defaults."""
        self._patch_basics(monkeypatch)
        # Menu: 0 = Exit
        monkeypatch.setattr(
            wizard_flow,
            "_input_int",
            lambda prompt, default, minimum, maximum, **kw: 0,
        )

        result = wizard_flow._build_subprofile("N")

        assert result.name is None
        assert result.standard == _wide_open_standard()
        assert result.random_suit_constraint is None
        assert result.partner_contingent_constraint is None
        assert result.opponents_contingent_suit_constraint is None

    def test_edit_standard_yes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Choose Standard (1), say yes to change, then exit."""
        self._patch_basics(monkeypatch)

        # Sequence: menu=1 (Standard), then menu=0 (Exit)
        int_calls: list[int] = [1, 0]
        int_idx = [0]

        def fake_input_int(prompt: str, default: int, minimum: int, maximum: int, **kw: object) -> int:
            idx = int_idx[0]
            int_idx[0] += 1
            if idx < len(int_calls):
                return int_calls[idx]
            return default

        monkeypatch.setattr(wizard_flow, "_input_int", fake_input_int)
        # Yes to "Change standard constraints?"
        monkeypatch.setattr(wizard_flow, "_yes_no", lambda prompt, default=True: True)

        new_std = _constrained_standard()
        monkeypatch.setattr(
            wizard_flow,
            "_build_standard_constraints",
            lambda existing=None, label_suffix="": new_std,
        )

        result = wizard_flow._build_subprofile("N")
        assert result.standard == new_std

    def test_skip_standard_edit_preserves(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Choose Standard (1), say no to change -> standard preserved."""
        self._patch_basics(monkeypatch)

        existing_std = _constrained_standard()
        existing = SubProfile(standard=existing_std, weight_percent=50.0)

        # Menu: 1 (Standard), then 0 (Exit)
        int_calls = [1, 0]
        int_idx = [0]

        def fake_input_int(prompt: str, default: int, minimum: int, maximum: int, **kw: object) -> int:
            idx = int_idx[0]
            int_idx[0] += 1
            if idx < len(int_calls):
                return int_calls[idx]
            return default

        monkeypatch.setattr(wizard_flow, "_input_int", fake_input_int)
        # No to "Change standard constraints?"
        monkeypatch.setattr(wizard_flow, "_yes_no", lambda prompt, default=True: False)

        result = wizard_flow._build_subprofile("N", existing=existing)
        assert result.standard == existing_std
        assert result.weight_percent == 50.0

    def test_set_rs_via_non_standard(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Choose Non-Standard (2), then RS (1), then back (0), then exit (0)."""
        self._patch_basics(monkeypatch)

        # Sequence: menu=2, ns_menu=1, ns_menu=0, menu=0
        int_calls = [2, 1, 0, 0]
        int_idx = [0]

        def fake_input_int(prompt: str, default: int, minimum: int, maximum: int, **kw: object) -> int:
            idx = int_idx[0]
            int_idx[0] += 1
            if idx < len(int_calls):
                return int_calls[idx]
            return default

        monkeypatch.setattr(wizard_flow, "_input_int", fake_input_int)

        rs = _dummy_rs()
        monkeypatch.setattr(
            wizard_flow,
            "_build_random_suit_constraint",
            lambda existing=None: rs,
        )

        result = wizard_flow._build_subprofile("N")
        assert result.random_suit_constraint is rs
        assert result.partner_contingent_constraint is None
        assert result.opponents_contingent_suit_constraint is None

    def test_replace_rs_with_pc_shows_warning(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Existing RS + choose PC → warning shown, RS cleared."""
        self._patch_basics(monkeypatch)

        existing = SubProfile(
            standard=_wide_open_standard(),
            random_suit_constraint=_dummy_rs(),
        )

        # Sequence: menu=2 (Non-Standard), ns=2 (PC), ns=0 (back), menu=0 (exit)
        int_calls = [2, 2, 0, 0]
        int_idx = [0]

        def fake_input_int(prompt: str, default: int, minimum: int, maximum: int, **kw: object) -> int:
            idx = int_idx[0]
            int_idx[0] += 1
            if idx < len(int_calls):
                return int_calls[idx]
            return default

        monkeypatch.setattr(wizard_flow, "_input_int", fake_input_int)

        pc = _dummy_pc()
        monkeypatch.setattr(
            wizard_flow,
            "_build_partner_contingent_constraint",
            lambda existing=None: pc,
        )

        result = wizard_flow._build_subprofile("N", existing=existing)

        # RS should be cleared, PC should be set
        assert result.random_suit_constraint is None
        assert result.partner_contingent_constraint is pc
        assert result.opponents_contingent_suit_constraint is None

        # Warning should have been printed
        captured = capsys.readouterr()
        assert "will replace" in captured.out
        assert "Random Suit" in captured.out

    def test_existing_name_preserved_on_enter(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Pressing Enter on name prompt preserves existing name."""
        monkeypatch.setattr(wizard_flow.wiz_io, "prompt_str", lambda prompt: "")
        monkeypatch.setattr(
            wizard_flow,
            "_input_int",
            lambda prompt, default, minimum, maximum, **kw: 0,
        )

        existing = SubProfile(standard=_wide_open_standard(), name="My Sub")
        result = wizard_flow._build_subprofile("N", existing=existing)
        assert result.name == "My Sub"

    def test_non_standard_shows_set_status(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Non-standard submenu shows [SET] for existing RS constraint."""
        self._patch_basics(monkeypatch)

        existing = SubProfile(
            standard=_wide_open_standard(),
            random_suit_constraint=_dummy_rs(),
        )

        # Menu: 2 (Non-Standard), then 0 (back), then 0 (exit)
        int_calls = [2, 0, 0]
        int_idx = [0]

        def fake_input_int(prompt: str, default: int, minimum: int, maximum: int, **kw: object) -> int:
            idx = int_idx[0]
            int_idx[0] += 1
            if idx < len(int_calls):
                return int_calls[idx]
            return default

        monkeypatch.setattr(wizard_flow, "_input_int", fake_input_int)

        wizard_flow._build_subprofile("N", existing=existing)

        captured = capsys.readouterr()
        assert "[SET]" in captured.out
        assert "[not set]" in captured.out
