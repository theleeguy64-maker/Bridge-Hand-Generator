# tests/test_profile_mgmt_menus.py
"""
Tests for the profile management and admin menu loops:
  - run_profile_manager() dispatches to all 7 actions
  - run_profile_manager() error recovery for wizard exceptions
  - admin_menu() dispatches to all 4 actions
  - admin_menu() exits immediately on 0
"""
from __future__ import annotations

from bridge_engine import profile_cli as pc
from bridge_engine import orchestrator
from bridge_engine import lin_tools


# ---------------------------------------------------------------------------
# run_profile_manager() — full dispatch
# ---------------------------------------------------------------------------

def test_profile_manager_dispatches_all_actions(monkeypatch, capsys):
    """
    Walking through choices 1-7 then 0 should call each action exactly once,
    then exit the loop cleanly.
    """
    calls = {
        "list": 0, "view": 0, "edit": 0,
        "create": 0, "delete": 0, "save_ver": 0, "help": 0,
    }

    monkeypatch.setattr(pc, "list_profiles_action", lambda: _inc(calls, "list"))
    monkeypatch.setattr(pc, "view_and_optional_print_profile_action", lambda: _inc(calls, "view"))
    monkeypatch.setattr(pc, "edit_profile_action", lambda: _inc(calls, "edit"))
    monkeypatch.setattr(pc, "create_profile_action", lambda: _inc(calls, "create"))
    monkeypatch.setattr(pc, "delete_profile_action", lambda: _inc(calls, "delete"))
    monkeypatch.setattr(pc, "save_as_new_version_action", lambda: _inc(calls, "save_ver"))
    monkeypatch.setattr(pc, "get_menu_help", lambda key: _inc(calls, "help") or "help text")

    # Choices: 1 through 7, then 0 to exit
    choices = iter([1, 2, 3, 4, 5, 6, 7, 0])
    monkeypatch.setattr(pc, "_input_int", lambda prompt, **kw: next(choices))

    pc.run_profile_manager()

    assert calls == {
        "list": 1, "view": 1, "edit": 1,
        "create": 1, "delete": 1, "save_ver": 1, "help": 1,
    }


def test_profile_manager_error_recovery(monkeypatch, capsys):
    """
    If edit_profile_action or create_profile_action raise an exception,
    the menu should catch it, print a warning, and continue to exit.
    """
    monkeypatch.setattr(pc, "edit_profile_action", _raise_value_error)
    monkeypatch.setattr(pc, "create_profile_action", _raise_runtime_error)

    # Choice 3 (edit, raises), choice 4 (create, raises), choice 0 (exit)
    choices = iter([3, 4, 0])
    monkeypatch.setattr(pc, "_input_int", lambda prompt, **kw: next(choices))

    pc.run_profile_manager()

    out = capsys.readouterr().out
    assert "Wizard error" in out
    assert "ValueError" in out
    assert "RuntimeError" in out


# ---------------------------------------------------------------------------
# admin_menu() — full dispatch
# ---------------------------------------------------------------------------

def test_admin_menu_dispatches_all_actions(monkeypatch, capsys):
    """
    Walking through choices 1-4 then 0 should call each action exactly once.
    """
    calls = {"lin": 0, "drafts": 0, "diag": 0, "help": 0}

    monkeypatch.setattr(lin_tools, "combine_lin_files_interactive", lambda: _inc(calls, "lin"))
    monkeypatch.setattr(pc, "run_draft_tools", lambda: _inc(calls, "drafts"))
    monkeypatch.setattr(
        orchestrator, "_run_profile_diagnostic_interactive",
        lambda: _inc(calls, "diag"),
    )
    monkeypatch.setattr(orchestrator, "get_menu_help", lambda key: _inc(calls, "help") or "help")

    # admin_menu imports _input_int directly, so patch on orchestrator module
    choices = iter([1, 2, 3, 4, 0])
    monkeypatch.setattr(orchestrator, "_input_int", lambda prompt, **kw: next(choices))

    orchestrator.admin_menu()

    assert calls == {"lin": 1, "drafts": 1, "diag": 1, "help": 1}


def test_admin_menu_exit_immediately(monkeypatch, capsys):
    """admin_menu with choice 0 should exit without calling any actions."""
    calls = {"lin": 0, "drafts": 0, "diag": 0}

    monkeypatch.setattr(lin_tools, "combine_lin_files_interactive", lambda: _inc(calls, "lin"))
    monkeypatch.setattr(pc, "run_draft_tools", lambda: _inc(calls, "drafts"))
    monkeypatch.setattr(
        orchestrator, "_run_profile_diagnostic_interactive",
        lambda: _inc(calls, "diag"),
    )

    # Immediately exit — patch on orchestrator module (direct import)
    monkeypatch.setattr(orchestrator, "_input_int", lambda prompt, **kw: 0)

    orchestrator.admin_menu()

    assert calls == {"lin": 0, "drafts": 0, "diag": 0}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _inc(d: dict, key: str) -> None:
    """Increment a counter in a tracking dict."""
    d[key] += 1


def _raise_value_error():
    raise ValueError("test boom")


def _raise_runtime_error():
    raise RuntimeError("wizard crash")
