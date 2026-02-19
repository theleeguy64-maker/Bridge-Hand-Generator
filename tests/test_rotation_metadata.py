"""
Rotation metadata integration tests.

Goal:
- Ensure rotate_deals_by_default always exists on created/edited profiles.
- Ensure *constraints-only* edit flow does NOT ask the rotation question (B2),
  and preserves existing rotation (or defaults True if missing).

These tests intentionally prevent any real stdin reads. If code tries to call
builtins.input(), the test should fail.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

import builtins
import pytest

from bridge_engine import cli_io
from bridge_engine import profile_cli
from bridge_engine import wizard_flow

# profile_wizard may or may not exist depending on refactors; tests adapt.
try:
    from bridge_engine import profile_wizard  # type: ignore
except Exception:  # pragma: no cover
    profile_wizard = None  # type: ignore


def _patch_if_hasattr(monkeypatch: pytest.MonkeyPatch, obj: Any, name: str, value: Any) -> None:
    if obj is None:
        return
    if hasattr(obj, name):
        monkeypatch.setattr(obj, name, value)


def _no_stdin(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(*a: Any, **k: Any) -> str:
        raise AssertionError("Test tried to read stdin via builtins.input()")

    monkeypatch.setattr(builtins, "input", _boom)


@dataclass
class DummySubProfile:
    # Only here so DummySeatProfile looks like the real thing.
    pass


class DummySeatProfile:
    def __init__(self) -> None:
        self.subprofiles = [DummySubProfile()]

    def to_dict(self) -> Dict[str, Any]:
        return {"subprofiles": []}


class DummyHandProfile:
    """
    Captures kwargs so tests can assert rotate_deals_by_default is always present.
    """

    created_kwargs: Dict[str, Any] = {}

    def __init__(self, **kwargs: Any) -> None:
        DummyHandProfile.created_kwargs = dict(kwargs)


def _patch_model_construction(monkeypatch: pytest.MonkeyPatch) -> None:
    # Patch HandProfile construction and validation at the call sites that exist.
    for mod in (wizard_flow, profile_cli, profile_wizard):
        _patch_if_hasattr(monkeypatch, mod, "HandProfile", DummyHandProfile)
        _patch_if_hasattr(monkeypatch, mod, "validate_profile", lambda profile: None)


def _patch_cli_io(monkeypatch: pytest.MonkeyPatch, *, rotate_answer: Optional[bool] = None) -> None:
    """
    Patch cli_io prompt helpers so nothing reads stdin.

    rotate_answer:
      - None  -> return defaults for all yes/no prompts
      - True/False -> when prompt includes 'Rotate deals by default', return that;
                      otherwise return defaults.
    """

    def fake_input_with_default(prompt: str, default: str = "") -> str:
        return default

    def fake_input_choice(prompt: str, options: list[str], default: Optional[str] = None, *a: Any, **k: Any) -> str:
        # fall back to first option if default isn't provided
        if default is None:
            return options[0]
        return default

    def fake_input_int(prompt: str, default: int, minimum: int, maximum: int, *a: Any, **k: Any) -> int:
        # always choose default; tolerate extra kwargs like show_range_suffix
        return default

    def fake_yes_no(prompt: str, default: bool = True) -> bool:
        if rotate_answer is not None and "Rotate deals by default" in prompt:
            return rotate_answer
        # For save prompts in CLI actions, default should be fine, but we prefer "no"
        # to keep the test side-effect free.
        if "Save this new profile" in prompt:
            return False
        return default

    monkeypatch.setattr(cli_io, "_input_with_default", fake_input_with_default)
    # _input_choice exists in this codebase; keep *args/**kwargs so refactors don't break tests.
    _patch_if_hasattr(monkeypatch, cli_io, "_input_choice", fake_input_choice)
    monkeypatch.setattr(cli_io, "_input_int", fake_input_int)
    monkeypatch.setattr(cli_io, "_yes_no", fake_yes_no)

    # Some modules bind helpers at import time; patch there too.
    _patch_if_hasattr(monkeypatch, profile_cli, "_yes_no", fake_yes_no)
    _patch_if_hasattr(
        monkeypatch, profile_cli, "prompt_yes_no", lambda prompt, default=True: fake_yes_no(prompt, default)
    )
    _patch_if_hasattr(monkeypatch, wizard_flow, "_yes_no", fake_yes_no)
    if hasattr(wizard_flow, "wiz_io"):
        _patch_if_hasattr(monkeypatch, wizard_flow.wiz_io, "_yes_no", fake_yes_no)  # type: ignore[attr-defined]


def _dummy_existing(*, rotate: Optional[bool]) -> Any:
    """
    Returns a minimal existing profile-like object for edit_constraints_interactive.
    """

    class Existing:
        def __init__(self) -> None:
            self.profile_name = "Existing"
            self.description = "Desc"
            self.tag = "Opener"
            self.dealer = "N"
            self.hand_dealing_order = ["N", "E", "S", "W"]
            self.seat_profiles = {s: DummySeatProfile() for s in ["N", "E", "S", "W"]}
            self.author = "Author"
            self.version = "0.1"
            self.subprofile_exclusions: list = []
            self.sort_order = None
            self.ns_role_mode = "no_driver_no_index"
            if rotate is not None:
                self.rotate_deals_by_default = rotate

    return Existing()


def test_create_profile_interactive_sets_rotate_flag(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """
    Create flow should always set rotate_deals_by_default on the constructed profile.
    """
    _no_stdin(monkeypatch)
    _patch_model_construction(monkeypatch)

    # Answer False to rotation prompt; accept defaults elsewhere.
    _patch_cli_io(monkeypatch, rotate_answer=False)

    # Avoid writing anything to disk if create action tries to save.
    _patch_if_hasattr(monkeypatch, profile_cli, "_save_profile_to_path", lambda profile, path: None)
    _patch_if_hasattr(monkeypatch, profile_cli, "_profile_path_for", lambda profile: tmp_path / "X.json")

    # Call whichever entry point exists in profile_cli.
    # Many refactors keep create_profile_action as the top-level.
    profile_cli.create_profile_action()

    created = DummyHandProfile.created_kwargs
    assert "rotate_deals_by_default" in created, "create flow must set rotate_deals_by_default"
    # If the prompt exists, our fake_yes_no returns False for that question.
    # If the prompt doesn't exist (unexpected), then created should still have a default.
    assert created["rotate_deals_by_default"] in (False, True)


def test_edit_constraints_interactive_preserves_existing_rotation(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Constraints-only edit should NOT ask the rotation question (B2) and should
    preserve existing.rotate_deals_by_default.
    """
    _no_stdin(monkeypatch)
    _patch_model_construction(monkeypatch)

    existing = _dummy_existing(rotate=False)

    # In constraints edit, we should skip editing each seat; return False for those prompts.
    def fake_yes_no(prompt: str, default: bool = True) -> bool:
        if "Do you want to edit constraints for seat" in prompt:
            return False
        if "Rotate deals by default" in prompt:
            raise AssertionError("Constraints-only edit must not prompt for rotation")
        return default

    monkeypatch.setattr(cli_io, "_yes_no", fake_yes_no)
    _patch_if_hasattr(monkeypatch, wizard_flow, "_yes_no", fake_yes_no)
    if hasattr(wizard_flow, "wiz_io"):
        _patch_if_hasattr(monkeypatch, wizard_flow.wiz_io, "_yes_no", fake_yes_no)  # type: ignore[attr-defined]

    # Make other inputs deterministic.
    monkeypatch.setattr(cli_io, "_input_with_default", lambda prompt, default="": default)
    _patch_if_hasattr(monkeypatch, cli_io, "_input_int", lambda prompt, default, minimum, maximum, *a, **k: default)

    wizard_flow.edit_constraints_interactive(existing)

    created = DummyHandProfile.created_kwargs
    assert created.get("rotate_deals_by_default") is False


def test_edit_constraints_interactive_defaults_rotation_true_if_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Back-compat: if existing profile doesn't have rotate_deals_by_default,
    constraints-only edit should still produce rotate_deals_by_default=True.
    """
    _no_stdin(monkeypatch)
    _patch_model_construction(monkeypatch)

    existing = _dummy_existing(rotate=None)

    def fake_yes_no(prompt: str, default: bool = True) -> bool:
        if "Do you want to edit constraints for seat" in prompt:
            return False
        if "Rotate deals by default" in prompt:
            raise AssertionError("Constraints-only edit must not prompt for rotation")
        return default

    monkeypatch.setattr(cli_io, "_yes_no", fake_yes_no)
    _patch_if_hasattr(monkeypatch, wizard_flow, "_yes_no", fake_yes_no)
    if hasattr(wizard_flow, "wiz_io"):
        _patch_if_hasattr(monkeypatch, wizard_flow.wiz_io, "_yes_no", fake_yes_no)  # type: ignore[attr-defined]

    monkeypatch.setattr(cli_io, "_input_with_default", lambda prompt, default="": default)
    _patch_if_hasattr(monkeypatch, cli_io, "_input_int", lambda prompt, default, minimum, maximum, *a, **k: default)

    wizard_flow.edit_constraints_interactive(existing)

    created = DummyHandProfile.created_kwargs
    assert created.get("rotate_deals_by_default") is True
