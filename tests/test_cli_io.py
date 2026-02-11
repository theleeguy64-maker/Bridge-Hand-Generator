# file: tests/test_cli_io.py
from __future__ import annotations

import builtins
from typing import List

from bridge_engine.cli_io import (
    _input_with_default,
    _input_int,
    _yes_no,
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