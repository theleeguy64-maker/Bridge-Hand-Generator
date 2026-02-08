from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

from bridge_engine.hand_profile import HandProfile
from bridge_engine import profile_cli as pc


def _make_dummy_profile(name: str = "Dummy") -> HandProfile:
    """Minimal HandProfile that satisfies HandProfile.__post_init__."""
    return HandProfile(
        profile_name=name,
        description="Test profile",
        dealer="N",
        hand_dealing_order=["N", "E", "S", "W"],
        tag="Opener",          # must be "Opener" or "Overcaller"
        seat_profiles={},      # we don't care for CLI tests
        author="Test",         # optional, but nice to keep realistic
        version="0.1",
    )


def test_list_profiles_action_prints_profile_names(monkeypatch, tmp_path, capsys):
    """list_profiles_action should list profiles returned by _load_profiles."""

    p1 = _make_dummy_profile("ProfileA")
    p2 = _make_dummy_profile("ProfileB")
    path1 = tmp_path / "ProfileA.json"
    path2 = tmp_path / "ProfileB.json"

    def fake_load_profiles() -> List[Tuple[Path, HandProfile]]:
        return [(path1, p1), (path2, p2)]

    monkeypatch.setattr(pc, "_load_profiles", fake_load_profiles)

    # Run
    capsys.readouterr()  # clear any prior output
    pc.list_profiles_action()
    captured = capsys.readouterr()

    # We don't care about exact formatting, just that names appear
    out = captured.out
    assert "ProfileA" in out
    assert "ProfileB" in out


def test_create_profile_action_calls_wizard_and_saves(monkeypatch, tmp_path, capsys):
    """
    create_profile_action should:
      - call create_profile_interactive to get a HandProfile
      - compute a path via _profile_path_for
      - pass both to _save_profile_to_path
    """

    created_profile = _make_dummy_profile("NewProfile")
    calls: dict[str, list] = {"saved": []}

    # Wizard stub: returns our dummy profile
    monkeypatch.setattr(pc, "create_profile_interactive", lambda: created_profile)

    # Path stub: ensure a deterministic path in tmp_dir
    def fake_profile_path_for(profile: HandProfile, base_dir: Path | None = None) -> Path:
        assert profile is created_profile
        return tmp_path / "NewProfile.json"

    monkeypatch.setattr(pc, "_profile_path_for", fake_profile_path_for)

    # Save stub: record calls instead of touching the real filesystem
    def fake_save_profile_to_path(profile: HandProfile, path: Path) -> None:
        calls["saved"].append((profile, path))

    monkeypatch.setattr(pc, "_save_profile_to_path", fake_save_profile_to_path)

    # 🔴 This is the missing piece: force "yes" so no real input() happens
    monkeypatch.setattr(pc, "_yes_no", lambda prompt, default=True: True)

    # Run
    capsys.readouterr()
    pc.create_profile_action()
    captured = capsys.readouterr()  # not asserted, just ensure no crash

    # Assert we saved exactly once, with the expected profile and path
    assert len(calls["saved"]) == 1
    saved_profile, saved_path = calls["saved"][0]
    assert saved_profile is created_profile
    assert saved_path == tmp_path / "NewProfile.json"


def test_view_and_optional_print_profile_action_uses_printer(monkeypatch, tmp_path, capsys):
    """
    view_and_optional_print_profile_action should:
      - load profiles
      - choose one
      - call _print_profile_metadata and _print_profile_constraints
        when the user says 'yes'
    """

    profile = _make_dummy_profile("ViewMe")
    path = tmp_path / "ViewMe.json"

    # Fake loader returns exactly one profile
    monkeypatch.setattr(pc, "_load_profiles", lambda: [(path, profile)])

    # Fake chooser returns that same profile directly (no real user selection)
    monkeypatch.setattr(pc, "_choose_profile", lambda profiles: (path, profile))

    # Make _yes_no always say "yes" so printing is triggered
    monkeypatch.setattr(pc, "_yes_no", lambda prompt, default=True: True)

    calls: dict[str, list] = {"metadata": [], "constraints": []}

    def fake_print_metadata(p: HandProfile, pth: Path) -> None:
        calls["metadata"].append((p, pth))

    def fake_print_constraints(p: HandProfile) -> None:
        calls["constraints"].append(p)

    monkeypatch.setattr(pc, "_print_profile_metadata", fake_print_metadata)
    monkeypatch.setattr(pc, "_print_profile_constraints", fake_print_constraints)

    # Run
    capsys.readouterr()
    pc.view_and_optional_print_profile_action()
    captured = capsys.readouterr()

    # Metadata is called once for summary, and once more for TXT export
    # (_yes_no always returns True, so TXT export is also triggered).
    assert len(calls["metadata"]) >= 1
    assert calls["metadata"][0] == (profile, path)

    # Constraints are called once for screen, and once more for TXT export.
    assert len(calls["constraints"]) >= 1
    assert calls["constraints"][0] is profile