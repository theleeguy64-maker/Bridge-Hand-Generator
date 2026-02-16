# tests/test_profile_mgmt_actions.py
"""
Tests for untested profile_cli action functions:
  - edit_profile_action (metadata, constraints, cancel)
  - delete_profile_action (confirm, cancel)
  - save_as_new_version_action
  - draft_tools_action (no drafts, delete one, delete all)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Tuple

from bridge_engine.hand_profile import HandProfile
from bridge_engine import profile_cli as pc
from bridge_engine import profile_store


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_profile(name: str = "TestProfile", **overrides) -> HandProfile:
    """Minimal valid HandProfile for action-level tests."""
    defaults = dict(
        profile_name=name,
        description="Test description",
        dealer="N",
        hand_dealing_order=["N", "E", "S", "W"],
        tag="Opener",
        seat_profiles={},
        author="Tester",
        version="0.1",
        ns_role_mode="north_drives",
    )
    defaults.update(overrides)
    return HandProfile(**defaults)


# ---------------------------------------------------------------------------
# edit_profile_action — metadata-only path (mode=1)
# ---------------------------------------------------------------------------


def test_edit_metadata_saves_updated_fields(monkeypatch, tmp_path, capsys):
    """
    edit_profile_action mode=1 should prompt for all metadata fields,
    construct a new HandProfile, and save it.
    """
    profile = _make_profile(ns_role_mode="north_drives")
    path = tmp_path / "TestProfile.json"

    # Stub profile loading + selection
    monkeypatch.setattr(pc, "_load_profiles", lambda: [(path, profile)])
    monkeypatch.setattr(pc, "_choose_profile", lambda profiles: (path, profile))

    # Capture what gets saved
    saved: list = []
    monkeypatch.setattr(pc, "_save_profile_to_path", lambda p, pth: saved.append((p, pth)))
    monkeypatch.setattr(profile_store, "delete_draft_for_canonical", lambda p: None)

    # Stub _input_int for mode selection (1 = metadata edit), ns_role_mode choice,
    # and loop exit (0 = done).  edit_profile_action() now loops, so call 3 = exit.
    call_count = {"input_int": 0}

    def fake_input_int(prompt, default=0, minimum=0, maximum=99, show_range_suffix=True):
        call_count["input_int"] += 1
        if call_count["input_int"] == 1:
            return 1  # mode = metadata edit
        if call_count["input_int"] == 2:
            return 5  # ns_role_mode choice — option 5 (no_driver_no_index)
        return 0  # exit the edit loop

    monkeypatch.setattr(pc, "_input_int", fake_input_int)

    # Stub _input_with_default for text prompts
    text_calls = {"n": 0}
    text_responses = ["Renamed", "New desc", "NewAuthor", "0.2"]

    def fake_input_with_default(prompt, default=""):
        idx = text_calls["n"]
        text_calls["n"] += 1
        if idx < len(text_responses):
            return text_responses[idx]
        return default

    monkeypatch.setattr(pc, "_input_with_default", fake_input_with_default)

    # Stub prompt_choice for tag and dealer
    choice_calls = {"n": 0}

    def fake_prompt_choice(prompt, choices, default=""):
        choice_calls["n"] += 1
        if choice_calls["n"] == 1:
            return "Overcaller"  # tag
        return "S"  # dealer

    monkeypatch.setattr(pc, "prompt_choice", fake_prompt_choice)

    # Stub _yes_no for rotate default
    monkeypatch.setattr(pc, "_yes_no", lambda prompt, default=True: False)

    # Stub input for dealing order (press Enter to keep current)
    monkeypatch.setattr("builtins.input", lambda prompt="": "")

    # Stub _profile_path_for so it returns a new versioned path
    new_path = tmp_path / "Renamed_v0.2.json"
    monkeypatch.setattr(pc, "_profile_path_for", lambda p, base_dir=None: new_path)

    # Run
    pc.edit_profile_action()

    # Assertions
    assert len(saved) == 1
    updated, saved_path = saved[0]
    # Version changed, so save goes to new path (old file kept)
    assert saved_path == new_path
    assert updated.profile_name == "Renamed"
    assert updated.description == "New desc"
    assert updated.tag == "Overcaller"
    assert updated.dealer == "S"
    assert updated.author == "NewAuthor"
    assert updated.version == "0.2"
    assert updated.rotate_deals_by_default is False
    assert updated.ns_role_mode == "no_driver_no_index"
    # Verify the 3 previously-missing fields are preserved (not reset to defaults)
    assert updated.subprofile_exclusions == list(profile.subprofile_exclusions)
    assert updated.is_invariants_safety_profile == profile.is_invariants_safety_profile
    assert updated.use_rs_w_only_path == profile.use_rs_w_only_path


# ---------------------------------------------------------------------------
# edit_profile_action — constraints-only path (mode=2)
# ---------------------------------------------------------------------------


def test_edit_constraints_delegates_to_wizard(monkeypatch, tmp_path, capsys):
    """
    edit_profile_action mode=2 should delegate to edit_constraints_interactive_flow
    and save the result when confirmed.
    """
    profile = _make_profile()
    path = tmp_path / "TestProfile.json"
    updated_profile = _make_profile(name="TestProfile", description="Updated constraints")

    monkeypatch.setattr(pc, "_load_profiles", lambda: [(path, profile)])
    monkeypatch.setattr(pc, "_choose_profile", lambda profiles: (path, profile))

    # Stub _input_int: mode=2 first call, then 0 to exit loop
    int_calls = {"n": 0}

    def fake_input_int(prompt, **kw):
        int_calls["n"] += 1
        if int_calls["n"] == 1:
            return 2  # mode = constraints edit
        return 0  # exit the edit loop

    monkeypatch.setattr(pc, "_input_int", fake_input_int)

    # Stub wizard call
    wizard_calls: list = []

    def fake_wizard(prof, profile_path=None):
        wizard_calls.append((prof, profile_path))
        return updated_profile

    monkeypatch.setattr(pc, "edit_constraints_interactive_flow", fake_wizard)

    # Confirm save
    monkeypatch.setattr(pc, "prompt_yes_no", lambda prompt, default=True: True)

    # Capture save
    saved: list = []
    monkeypatch.setattr(pc, "_save_profile_to_path", lambda p, pth: saved.append((p, pth)))
    monkeypatch.setattr(profile_store, "delete_draft_for_canonical", lambda p: None)

    pc.edit_profile_action()

    assert len(wizard_calls) == 1
    assert wizard_calls[0] == (profile, path)
    assert len(saved) == 1
    assert saved[0][0] is updated_profile


# ---------------------------------------------------------------------------
# edit_profile_action — cancel path (mode=0)
# ---------------------------------------------------------------------------


def test_edit_cancel_does_not_save(monkeypatch, tmp_path, capsys):
    """edit_profile_action mode=0 should cancel without saving."""
    profile = _make_profile()
    path = tmp_path / "TestProfile.json"

    monkeypatch.setattr(pc, "_load_profiles", lambda: [(path, profile)])
    monkeypatch.setattr(pc, "_choose_profile", lambda profiles: (path, profile))

    # mode=0 (cancel)
    monkeypatch.setattr(pc, "_input_int", lambda prompt, **kw: 0)

    saved: list = []
    monkeypatch.setattr(pc, "_save_profile_to_path", lambda p, pth: saved.append(1))

    pc.edit_profile_action()

    assert len(saved) == 0


# ---------------------------------------------------------------------------
# delete_profile_action — confirm and cancel
# ---------------------------------------------------------------------------


def test_delete_profile_confirm(monkeypatch, tmp_path, capsys):
    """delete_profile_action should remove file when user confirms."""
    profile = _make_profile()
    path = tmp_path / "TestProfile.json"
    path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(pc, "_load_profiles", lambda: [(path, profile)])
    monkeypatch.setattr(pc, "_choose_profile", lambda profiles: (path, profile))
    monkeypatch.setattr(pc, "prompt_yes_no", lambda prompt, default=True: True)

    pc.delete_profile_action()

    assert not path.exists()
    assert "Deleted" in capsys.readouterr().out


def test_delete_profile_cancel(monkeypatch, tmp_path, capsys):
    """delete_profile_action should keep file when user cancels."""
    profile = _make_profile()
    path = tmp_path / "TestProfile.json"
    path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(pc, "_load_profiles", lambda: [(path, profile)])
    monkeypatch.setattr(pc, "_choose_profile", lambda profiles: (path, profile))
    monkeypatch.setattr(pc, "prompt_yes_no", lambda prompt, default=True: False)

    pc.delete_profile_action()

    assert path.exists()


# ---------------------------------------------------------------------------
# save_as_new_version_action
# ---------------------------------------------------------------------------


def test_save_as_new_version_preserves_all_fields(monkeypatch, tmp_path, capsys):
    """
    save_as_new_version_action should create a new HandProfile with updated
    version but all other fields preserved (including the 5 metadata fields
    that were previously missing).
    """
    profile = _make_profile(
        ns_role_mode="south_drives",
        rotate_deals_by_default=False,
    )
    path = tmp_path / "TestProfile.json"

    monkeypatch.setattr(pc, "_load_profiles", lambda: [(path, profile)])
    monkeypatch.setattr(pc, "_choose_profile", lambda profiles: (path, profile))

    # Stub version input
    monkeypatch.setattr(pc, "_input_with_default", lambda prompt, default="": "0.2")

    # Stub validate (no-op)
    monkeypatch.setattr(pc, "validate_profile", lambda p: p)

    # Stub path + save
    monkeypatch.setattr(pc, "_profile_path_for", lambda p, base_dir=None: tmp_path / "new.json")

    saved: list = []
    monkeypatch.setattr(pc, "_save_profile_to_path", lambda p, pth: saved.append((p, pth)))
    monkeypatch.setattr(profile_store, "delete_draft_for_canonical", lambda p: None)

    pc.save_as_new_version_action()

    assert len(saved) == 1
    new_profile, _ = saved[0]
    assert new_profile.version == "0.2"
    # All other fields preserved from original
    assert new_profile.profile_name == profile.profile_name
    assert new_profile.description == profile.description
    assert new_profile.dealer == profile.dealer
    assert new_profile.tag == profile.tag
    assert new_profile.author == profile.author
    assert new_profile.ns_role_mode == "south_drives"
    assert new_profile.rotate_deals_by_default is False
    assert new_profile.subprofile_exclusions == list(profile.subprofile_exclusions)
    assert new_profile.is_invariants_safety_profile == profile.is_invariants_safety_profile
    assert new_profile.use_rs_w_only_path == profile.use_rs_w_only_path


# ---------------------------------------------------------------------------
# draft_tools_action
# ---------------------------------------------------------------------------


def test_draft_tools_no_drafts(monkeypatch, capsys):
    """draft_tools_action should print 'No draft' when no drafts exist."""
    monkeypatch.setattr(profile_store, "list_drafts", lambda d: [])
    monkeypatch.setattr(pc, "_profiles_dir", lambda: Path("/fake"))

    pc.draft_tools_action()

    assert "No draft" in capsys.readouterr().out


def test_draft_tools_delete_one(monkeypatch, tmp_path, capsys):
    """draft_tools_action action=1 should delete only the chosen draft."""
    draft1 = tmp_path / "Alpha_TEST.json"
    draft2 = tmp_path / "Beta_TEST.json"
    draft1.write_text("{}", encoding="utf-8")
    draft2.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(pc, "_profiles_dir", lambda: tmp_path)
    monkeypatch.setattr(profile_store, "list_drafts", lambda d: [draft1, draft2])

    # _input_int calls: action=1 (delete one), which draft=1
    int_calls = {"n": 0}

    def fake_input_int(prompt, default=0, minimum=0, maximum=99, show_range_suffix=True):
        int_calls["n"] += 1
        return 1  # first call: action=1, second call: draft #1

    monkeypatch.setattr(pc, "_input_int", fake_input_int)

    # Confirm deletion
    monkeypatch.setattr(pc, "prompt_yes_no", lambda prompt, default=True: True)

    pc.draft_tools_action()

    assert not draft1.exists()
    assert draft2.exists()
    assert "Deleted" in capsys.readouterr().out


def test_draft_tools_delete_all(monkeypatch, tmp_path, capsys):
    """draft_tools_action action=2 should delete all drafts when confirmed."""
    draft1 = tmp_path / "Alpha_TEST.json"
    draft2 = tmp_path / "Beta_TEST.json"
    draft1.write_text("{}", encoding="utf-8")
    draft2.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(pc, "_profiles_dir", lambda: tmp_path)
    monkeypatch.setattr(profile_store, "list_drafts", lambda d: [draft1, draft2])

    # _input_int: action=2 (delete all)
    monkeypatch.setattr(pc, "_input_int", lambda prompt, **kw: 2)

    # Confirm
    monkeypatch.setattr(pc, "prompt_yes_no", lambda prompt, default=True: True)

    pc.draft_tools_action()

    assert not draft1.exists()
    assert not draft2.exists()
    out = capsys.readouterr().out
    assert "Deleted 2 draft(s)" in out
