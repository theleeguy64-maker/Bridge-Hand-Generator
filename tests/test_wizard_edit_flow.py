# tests/test_wizard_edit_flow.py
"""
Tests for the wizard constraint editing flow:
  - _build_profile(existing=...) skips all seats
  - _build_profile(existing=...) edits one seat
  - _build_profile(existing=...) triggers autosave
  - edit_constraints_interactive() roundtrip
  - _edit_subprofile_exclusions_for_seat() adds an exclusion
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from bridge_engine.hand_profile import (
    HandProfile,
    SeatProfile,
    StandardSuitConstraints,
    SubProfile,
    SubprofileExclusionData,
    SuitRange,
    validate_profile,
)
from bridge_engine import profile_wizard
from bridge_engine import wizard_flow
from bridge_engine import profile_store


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_full_profile(name: str = "EditTest") -> HandProfile:
    """HandProfile with real open seat profiles for all 4 seats."""
    seat_profiles = {}
    sr = SuitRange()
    for seat in ("N", "E", "S", "W"):
        std = StandardSuitConstraints(spades=sr, hearts=sr, diamonds=sr, clubs=sr)
        sub = SubProfile(
            standard=std,
            weight_percent=100.0,
            ns_role_usage="any",
        )
        seat_profiles[seat] = SeatProfile(seat=seat, subprofiles=[sub])
    return HandProfile(
        profile_name=name,
        description="Test profile for editing",
        dealer="N",
        hand_dealing_order=["N", "E", "S", "W"],
        tag="Opener",
        seat_profiles=seat_profiles,
        author="Tester",
        version="0.1",
        ns_role_mode="north_drives",
    )


# ---------------------------------------------------------------------------
# Test 1: Skip all seats — profile preserved
# ---------------------------------------------------------------------------

def test_edit_skip_all_seats_preserves_profile(monkeypatch, capsys):
    """
    When the user says 'no' to editing every seat, _build_profile should
    return kwargs with identical seat_profiles to the original.
    """
    profile = _make_full_profile()

    # _yes_no via profile_wizard: always False (skip editing each seat)
    monkeypatch.setattr(profile_wizard, "_yes_no", lambda prompt, default=True: False)

    # clear_screen no-op (wizard calls it at start of edit flow)
    monkeypatch.setattr(profile_wizard, "clear_screen", lambda: None)

    result = wizard_flow._build_profile(existing=profile)

    # All 4 seat profiles should be preserved
    assert set(result["seat_profiles"].keys()) == {"N", "E", "S", "W"}
    for seat in ("N", "E", "S", "W"):
        assert result["seat_profiles"][seat] is profile.seat_profiles[seat]

    # Metadata preserved
    assert result["profile_name"] == profile.profile_name
    assert result["dealer"] == profile.dealer
    assert result["ns_role_mode"] == "north_drives"
    assert result["rotate_deals_by_default"] is True


# ---------------------------------------------------------------------------
# Test 2: Edit one seat, skip others
# ---------------------------------------------------------------------------

def test_edit_one_seat_updates_only_that_seat(monkeypatch, capsys):
    """
    When user edits only N (first in dealing order), other seats should
    be preserved unchanged.
    """
    profile = _make_full_profile()

    # Modified N seat profile (different HCP range)
    sr = SuitRange()
    new_std = StandardSuitConstraints(spades=sr, hearts=sr, diamonds=sr, clubs=sr,
                                      total_min_hcp=10, total_max_hcp=15)
    new_sub = SubProfile(standard=new_std, weight_percent=100.0, ns_role_usage="any")
    new_n_seat = SeatProfile(seat="N", subprofiles=[new_sub])

    # _yes_no: True for N (first call), False for E/S/W (next 3 calls)
    # Also False for exclusion editing prompt after N
    yes_no_calls = iter([True, False, False, False, False])
    monkeypatch.setattr(
        profile_wizard, "_yes_no",
        lambda prompt, default=True: next(yes_no_calls),
    )

    # _build_seat_profile: return our modified seat profile for N
    monkeypatch.setattr(
        profile_wizard, "_build_seat_profile",
        lambda seat, existing_sp: new_n_seat,
    )

    monkeypatch.setattr(profile_wizard, "clear_screen", lambda: None)

    result = wizard_flow._build_profile(existing=profile)

    # N should be the new seat profile
    assert result["seat_profiles"]["N"] is new_n_seat
    # E, S, W should be the originals
    for seat in ("E", "S", "W"):
        assert result["seat_profiles"][seat] is profile.seat_profiles[seat]


# ---------------------------------------------------------------------------
# Test 3: Autosave triggered when original_path is provided
# ---------------------------------------------------------------------------

def test_edit_triggers_autosave(monkeypatch, tmp_path, capsys):
    """
    When _build_profile is called with original_path, editing a seat
    should trigger _autosave_profile_draft.
    """
    profile = _make_full_profile()
    original_path = tmp_path / "EditTest.json"

    # Edit N, skip E/S/W
    yes_no_calls = iter([True, False, False, False, False])
    monkeypatch.setattr(
        profile_wizard, "_yes_no",
        lambda prompt, default=True: next(yes_no_calls),
    )

    # Return existing seat unchanged
    monkeypatch.setattr(
        profile_wizard, "_build_seat_profile",
        lambda seat, existing_sp: existing_sp or SeatProfile(seat=seat, subprofiles=[
            SubProfile(standard=StandardSuitConstraints(
                spades=SuitRange(), hearts=SuitRange(), diamonds=SuitRange(), clubs=SuitRange()))
        ]),
    )

    monkeypatch.setattr(profile_wizard, "clear_screen", lambda: None)

    # Track autosave calls
    autosave_calls: list = []
    monkeypatch.setattr(
        wizard_flow, "_autosave_profile_draft",
        lambda snapshot, path: autosave_calls.append((snapshot, path)),
    )

    result = wizard_flow._build_profile(
        existing=profile,
        original_path=original_path,
    )

    # Autosave should have been called at least once (after editing N)
    assert len(autosave_calls) >= 1
    snapshot, saved_path = autosave_calls[0]
    assert saved_path == original_path
    assert isinstance(snapshot, HandProfile)
    assert snapshot.profile_name == profile.profile_name


# ---------------------------------------------------------------------------
# Test 4: edit_constraints_interactive roundtrip (skip all)
# ---------------------------------------------------------------------------

def test_edit_constraints_roundtrip(monkeypatch, capsys):
    """
    edit_constraints_interactive with all seats skipped should return
    a valid HandProfile that matches the original.
    """
    profile = _make_full_profile()

    # Skip all seats
    monkeypatch.setattr(profile_wizard, "_yes_no", lambda prompt, default=True: False)
    monkeypatch.setattr(profile_wizard, "clear_screen", lambda: None)

    # validate_profile is called inside edit_constraints_interactive
    # but our profile is already valid, so it should pass

    result = wizard_flow.edit_constraints_interactive(existing=profile)

    assert isinstance(result, HandProfile)
    assert result.profile_name == profile.profile_name
    assert result.dealer == profile.dealer
    assert result.ns_role_mode == "north_drives"
    assert set(result.seat_profiles.keys()) == {"N", "E", "S", "W"}
    for seat in ("N", "E", "S", "W"):
        assert result.seat_profiles[seat] is profile.seat_profiles[seat]


# ---------------------------------------------------------------------------
# Test 5: Exclusion editing adds an exclusion
# ---------------------------------------------------------------------------

def test_exclusion_editing_adds_exclusion(monkeypatch, capsys):
    """
    When the user edits N and adds an exclusion, the returned kwargs
    should include the new exclusion in subprofile_exclusions.
    """
    profile = _make_full_profile()

    # _yes_no sequence:
    # 1. Edit N? → True
    # 2. (exclusion editing is called internally — see _edit_subprofile_exclusions_for_seat)
    #    We need to handle the exclusion prompts too
    # 3. Edit E? → False
    # 4. Edit S? → False
    # 5. Edit W? → False
    #
    # _edit_subprofile_exclusions_for_seat internally asks:
    #   - "Add/edit sub-profile exclusions for seat N?" → True
    #   - (if existing exclusions: "Remove any?" → no)
    #   - "Add another exclusion?" → yes first time, no second time
    #
    # To keep this simple, we'll monkeypatch _edit_subprofile_exclusions_for_seat
    # directly to return a list with one exclusion.

    dummy_exclusion = SubprofileExclusionData(
        seat="N",
        subprofile_index=1,
        excluded_shapes=["4333"],
    )

    # _yes_no: True for N (edit), False for E/S/W
    yes_no_calls = iter([True, False, False, False])
    monkeypatch.setattr(
        profile_wizard, "_yes_no",
        lambda prompt, default=True: next(yes_no_calls),
    )

    # _build_seat_profile: return existing unchanged
    monkeypatch.setattr(
        profile_wizard, "_build_seat_profile",
        lambda seat, existing_sp: existing_sp,
    )

    monkeypatch.setattr(profile_wizard, "clear_screen", lambda: None)

    # Stub _edit_subprofile_exclusions_for_seat to return our dummy exclusion
    monkeypatch.setattr(
        wizard_flow, "_edit_subprofile_exclusions_for_seat",
        lambda existing, seat, seat_profiles, hand_dealing_order, current_all: [dummy_exclusion],
    )

    result = wizard_flow._build_profile(existing=profile)

    assert len(result["subprofile_exclusions"]) == 1
    assert result["subprofile_exclusions"][0] is dummy_exclusion
    assert result["subprofile_exclusions"][0].seat == "N"
    assert result["subprofile_exclusions"][0].excluded_shapes == ["4333"]
