# file: tests/test_cli_io.py
from __future__ import annotations

import builtins
from typing import List

from bridge_engine.cli_io import (
    _input_with_default,
    _input_int,
    _yes_no,
    _yes_no_help,
)


def test_input_with_default_uses_default_on_empty(monkeypatch):
    def fake_input(prompt: str) -> str:
        return ""  # simulate pressing Enter

    monkeypatch.setattr(builtins, "input", fake_input)
    result = _input_with_default("Name", default="Lee")
    assert result == "Lee"


def test_input_with_default_returns_value(monkeypatch):
    def fake_input(prompt: str) -> str:
        return "Guy"

    monkeypatch.setattr(builtins, "input", fake_input)
    result = _input_with_default("Surname", default="X")
    assert result == "Guy"


def test_input_int_within_bounds(monkeypatch):
    answers: List[str] = ["15"]

    def fake_input(prompt: str) -> str:
        return answers.pop(0)

    monkeypatch.setattr(builtins, "input", fake_input)
    value = _input_int("HCP", minimum=0, maximum=37)
    assert value == 15


def test_input_int_uses_default(monkeypatch):
    answers: List[str] = [""]  # hit Enter

    def fake_input(prompt: str) -> str:
        return answers.pop(0)

    monkeypatch.setattr(builtins, "input", fake_input)
    value = _input_int("HCP", default=12, minimum=0, maximum=37)
    assert value == 12


def test_yes_no_defaults(monkeypatch):
    # default True
    def fake_input(prompt: str) -> str:
        return ""

    monkeypatch.setattr(builtins, "input", fake_input)
    assert _yes_no("Proceed?", default=True) is True

    # default False
    def fake_input2(prompt: str) -> str:
        return ""

    monkeypatch.setattr(builtins, "input", fake_input2)
    assert _yes_no("Proceed?", default=False) is False


def test_yes_no_explicit_answers(monkeypatch):
    answers: List[str] = ["y", "N"]

    def fake_input(prompt: str) -> str:
        return answers.pop(0)

    monkeypatch.setattr(builtins, "input", fake_input)

    assert _yes_no("OK?", default=False) is True
    assert _yes_no("OK?", default=True) is False


# --- _yes_no_help tests ---


def test_yes_no_help_defaults(monkeypatch):
    """Empty input returns the default value."""
    monkeypatch.setattr(builtins, "input", lambda _: "")
    assert _yes_no_help("Q?", "main_menu", default=True) is True

    monkeypatch.setattr(builtins, "input", lambda _: "")
    assert _yes_no_help("Q?", "main_menu", default=False) is False


def test_yes_no_help_explicit_answers(monkeypatch):
    """Explicit y/n answers work the same as _yes_no."""
    answers: List[str] = ["y", "N"]
    monkeypatch.setattr(builtins, "input", lambda _: answers.pop(0))

    assert _yes_no_help("Q?", "main_menu", default=False) is True
    assert _yes_no_help("Q?", "main_menu", default=True) is False


def test_yes_no_help_shows_help_and_reprompts(monkeypatch, capsys):
    """Typing 'help' prints help text and re-prompts; then accepts y/n."""
    answers: List[str] = ["help", "y"]
    monkeypatch.setattr(builtins, "input", lambda _: answers.pop(0))

    result = _yes_no_help("Q?", "main_menu", default=False)
    assert result is True

    captured = capsys.readouterr()
    # Should contain something from the main_menu help text
    assert "Main Menu" in captured.out


def test_yes_no_help_accepts_question_mark(monkeypatch, capsys):
    """'?' is an alias for 'help'."""
    answers: List[str] = ["?", "n"]
    monkeypatch.setattr(builtins, "input", lambda _: answers.pop(0))

    result = _yes_no_help("Q?", "main_menu", default=True)
    assert result is False

    captured = capsys.readouterr()
    assert "Main Menu" in captured.out


def test_yes_no_help_accepts_h_shortcut(monkeypatch, capsys):
    """'h' is an alias for 'help'."""
    answers: List[str] = ["h", "yes"]
    monkeypatch.setattr(builtins, "input", lambda _: answers.pop(0))

    result = _yes_no_help("Q?", "main_menu", default=False)
    assert result is True

    captured = capsys.readouterr()
    assert "Main Menu" in captured.out


def test_yes_no_help_invalid_then_valid(monkeypatch, capsys):
    """Invalid input prints error to stderr, then accepts valid input."""
    answers: List[str] = ["maybe", "y"]
    monkeypatch.setattr(builtins, "input", lambda _: answers.pop(0))

    result = _yes_no_help("Q?", "main_menu", default=False)
    assert result is True

    captured = capsys.readouterr()
    assert "y, n, or help" in captured.err


def test_yes_no_help_unknown_key_fallback(monkeypatch, capsys):
    """Unknown help_key returns the generic fallback text."""
    answers: List[str] = ["help", "n"]
    monkeypatch.setattr(builtins, "input", lambda _: answers.pop(0))

    result = _yes_no_help("Q?", "nonexistent_key", default=True)
    assert result is False

    captured = capsys.readouterr()
    assert "No further help" in captured.out
