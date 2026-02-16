# tests/test_cli_entrypoints.py
from __future__ import annotations

import builtins
from typing import List

from bridge_engine import orchestrator


def test_orchestrator_main_calls_main_menu(monkeypatch):
    calls: List[str] = []

    def fake_main_menu() -> None:
        calls.append("main_menu")

    monkeypatch.setattr(orchestrator, "main_menu", fake_main_menu)

    orchestrator.main()

    assert calls == ["main_menu"]
