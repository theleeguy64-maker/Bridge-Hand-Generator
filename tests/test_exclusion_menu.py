# tests/test_exclusion_menu.py
"""
Tests for the exclusion menu loop in wizard_flow._edit_subprofile_exclusions_for_seat.

Covers menu choices:
  0) Exit — exits without adding exclusions
  1) Add shapes exclusion — appends a shapes-based exclusion
  2) Add rule exclusion — appends a rule-based exclusion
  3) Help — prints help text, loops back without adding
"""

from __future__ import annotations

from bridge_engine.hand_profile import (
    HandProfile,
    SeatProfile,
    StandardSuitConstraints,
    SubProfile,
    SubprofileExclusionData,
    SubprofileExclusionClause,
    SuitRange,
)
from bridge_engine import profile_wizard
from bridge_engine import wizard_flow
from bridge_engine.menu_help import get_menu_help


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_seat_profiles():
    """Minimal seat_profiles dict with one sub-profile per seat."""
    sr = SuitRange()
    profiles = {}
    for seat in ("N", "E", "S", "W"):
        std = StandardSuitConstraints(spades=sr, hearts=sr, diamonds=sr, clubs=sr)
        sub = SubProfile(standard=std, weight_percent=100.0, ns_role_usage="any")
        profiles[seat] = SeatProfile(seat=seat, subprofiles=[sub])
    return profiles


# ---------------------------------------------------------------------------
# Test: choice 0 — Exit immediately, no exclusions added
# ---------------------------------------------------------------------------


def test_menu_exit_adds_nothing(monkeypatch):
    """
    When user picks 0 (Exit) on the exclusion menu, no exclusions should
    be added. The function should return the original list unchanged.
    """
    seat_profiles = _make_seat_profiles()

    # _yes_no / _yes_no_help: "Add/edit exclusions for seat N?" → True
    monkeypatch.setattr(profile_wizard, "_yes_no", lambda prompt, default=True: True)
    monkeypatch.setattr(profile_wizard, "_yes_no_help", lambda prompt, key, default=True: True)

    # _input_int calls:
    #   1) sub-profile index → 1
    #   2) menu choice → 0 (exit)
    int_calls = {"n": 0}

    def fake_input_int(prompt, default=0, minimum=0, maximum=99, show_range_suffix=True):
        int_calls["n"] += 1
        if int_calls["n"] == 1:
            return 1  # sub-profile index
        return 0  # menu choice: exit

    monkeypatch.setattr(profile_wizard, "_input_int", fake_input_int)

    result = wizard_flow._edit_subprofile_exclusions_for_seat(
        existing=None,
        seat="N",
        seat_profiles=seat_profiles,
        current_all=[],
    )

    assert result == []


# ---------------------------------------------------------------------------
# Test: choice 1 — Add shapes exclusion
# ---------------------------------------------------------------------------


def test_menu_shapes_adds_exclusion(monkeypatch):
    """
    When user picks 1 (Shapes), enters shape patterns, then 0 (Exit),
    one shapes-based exclusion should be returned.
    """
    seat_profiles = _make_seat_profiles()

    monkeypatch.setattr(profile_wizard, "_yes_no", lambda prompt, default=True: True)
    monkeypatch.setattr(profile_wizard, "_yes_no_help", lambda prompt, key, default=True: True)

    # _input_int calls:
    #   1) sub-profile index → 1
    #   2) menu choice → 1 (shapes)
    #   3) menu choice → 0 (exit)
    int_calls = {"n": 0}

    def fake_input_int(prompt, default=0, minimum=0, maximum=99, show_range_suffix=True):
        int_calls["n"] += 1
        if int_calls["n"] == 1:
            return 1  # sub-profile index
        if int_calls["n"] == 2:
            return 1  # menu: add shapes
        return 0  # menu: exit

    monkeypatch.setattr(profile_wizard, "_input_int", fake_input_int)

    # _input_with_default: shapes CSV prompt → "4333,4432"
    monkeypatch.setattr(
        profile_wizard,
        "_input_with_default",
        lambda prompt, default="": "4333,4432",
    )

    result = wizard_flow._edit_subprofile_exclusions_for_seat(
        existing=None,
        seat="E",
        seat_profiles=seat_profiles,
        current_all=[],
    )

    assert len(result) == 1
    exc = result[0]
    assert exc.seat == "E"
    assert exc.subprofile_index == 1
    assert exc.excluded_shapes == ["4333", "4432"]
    assert exc.clauses is None


# ---------------------------------------------------------------------------
# Test: choice 2 — Add rule exclusion
# ---------------------------------------------------------------------------


def test_menu_rule_adds_exclusion(monkeypatch):
    """
    When user picks 2 (Rule), enters clause details, then 0 (Exit),
    one rule-based exclusion should be returned.
    """
    seat_profiles = _make_seat_profiles()

    # _yes_no_help: "Add/edit exclusions for seat S?" → True
    monkeypatch.setattr(profile_wizard, "_yes_no_help", lambda prompt, key, default=True: True)

    # _yes_no: "Add a second clause?" → False (stop at 1 clause)
    monkeypatch.setattr(profile_wizard, "_yes_no", lambda prompt, default=True: False)

    # _input_int calls:
    #   1) sub-profile index → 1
    #   2) menu choice → 2 (rule)
    #   3) clause 1 length_eq → 4
    #   4) clause 1 count → 2
    #   5) menu choice → 0 (exit)
    int_calls = {"n": 0}
    int_responses = [1, 2, 4, 2, 0]

    def fake_input_int(prompt, default=0, minimum=0, maximum=99, show_range_suffix=True):
        idx = int_calls["n"]
        int_calls["n"] += 1
        return int_responses[idx]

    monkeypatch.setattr(profile_wizard, "_input_int", fake_input_int)

    # _input_choice: clause group → "MAJOR" (defined in wizard_flow, not profile_wizard)
    monkeypatch.setattr(
        wizard_flow,
        "_input_choice",
        lambda prompt, options, default=None: "MAJOR",
    )

    result = wizard_flow._edit_subprofile_exclusions_for_seat(
        existing=None,
        seat="S",
        seat_profiles=seat_profiles,
        current_all=[],
    )

    assert len(result) == 1
    exc = result[0]
    assert exc.seat == "S"
    assert exc.subprofile_index == 1
    assert exc.excluded_shapes is None
    assert len(exc.clauses) == 1
    assert exc.clauses[0].group == "MAJOR"
    assert exc.clauses[0].length_eq == 4
    assert exc.clauses[0].count == 2


# ---------------------------------------------------------------------------
# Test: choice 3 — Help prints text, loops back
# ---------------------------------------------------------------------------


def test_menu_help_prints_text_and_loops(monkeypatch, capsys):
    """
    When user picks 3 (Help), help text should be printed and no
    exclusions added. The menu should loop back so the user can exit.
    """
    seat_profiles = _make_seat_profiles()

    monkeypatch.setattr(profile_wizard, "_yes_no", lambda prompt, default=True: True)
    monkeypatch.setattr(profile_wizard, "_yes_no_help", lambda prompt, key, default=True: True)

    # _input_int calls:
    #   1) sub-profile index → 1
    #   2) menu choice → 3 (help)
    #   3) menu choice → 0 (exit)
    int_calls = {"n": 0}

    def fake_input_int(prompt, default=0, minimum=0, maximum=99, show_range_suffix=True):
        int_calls["n"] += 1
        if int_calls["n"] == 1:
            return 1  # sub-profile index
        if int_calls["n"] == 2:
            return 3  # menu: help
        return 0  # menu: exit

    monkeypatch.setattr(profile_wizard, "_input_int", fake_input_int)

    result = wizard_flow._edit_subprofile_exclusions_for_seat(
        existing=None,
        seat="W",
        seat_profiles=seat_profiles,
        current_all=[],
    )

    # No exclusions added
    assert result == []

    # Help text was printed
    captured = capsys.readouterr().out
    expected_help = get_menu_help("exclusions")
    assert expected_help in captured


# ---------------------------------------------------------------------------
# Test: multiple additions — shapes then rule, then exit
# ---------------------------------------------------------------------------


def test_menu_multiple_additions(monkeypatch):
    """
    User adds one shapes exclusion, then one rule exclusion, then exits.
    Both exclusions should be in the returned list.
    """
    seat_profiles = _make_seat_profiles()

    # _yes_no_help: "Add/edit exclusions for seat N?" → True
    monkeypatch.setattr(profile_wizard, "_yes_no_help", lambda prompt, key, default=True: True)
    # _yes_no: "Add a second clause?" → False
    monkeypatch.setattr(profile_wizard, "_yes_no", lambda prompt, default=True: False)

    # _input_int calls:
    #   1) sub-profile index → 1
    #   2) menu choice → 1 (shapes)
    #   3) menu choice → 2 (rule)
    #   4) clause 1 length_eq → 3
    #   5) clause 1 count → 4
    #   6) menu choice → 0 (exit)
    int_calls = {"n": 0}
    int_responses = [1, 1, 2, 3, 4, 0]

    def fake_input_int(prompt, default=0, minimum=0, maximum=99, show_range_suffix=True):
        idx = int_calls["n"]
        int_calls["n"] += 1
        return int_responses[idx]

    monkeypatch.setattr(profile_wizard, "_input_int", fake_input_int)

    # _input_with_default: shapes CSV
    monkeypatch.setattr(
        profile_wizard,
        "_input_with_default",
        lambda prompt, default="": "5332",
    )

    # _input_choice: clause group → "ANY" (defined in wizard_flow, not profile_wizard)
    monkeypatch.setattr(
        wizard_flow,
        "_input_choice",
        lambda prompt, options, default=None: "ANY",
    )

    result = wizard_flow._edit_subprofile_exclusions_for_seat(
        existing=None,
        seat="N",
        seat_profiles=seat_profiles,
        current_all=[],
    )

    assert len(result) == 2

    # First: shapes exclusion
    assert result[0].excluded_shapes == ["5332"]
    assert result[0].clauses is None

    # Second: rule exclusion
    assert result[1].excluded_shapes is None
    assert len(result[1].clauses) == 1
    assert result[1].clauses[0].group == "ANY"
    assert result[1].clauses[0].length_eq == 3
    assert result[1].clauses[0].count == 4
