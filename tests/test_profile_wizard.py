# file: tests/test_profile_wizard.py
from typing import List
import builtins

from bridge_engine.profile_wizard import _build_suit_range_for_prompt
from bridge_engine.hand_profile import SuitRange


def test_build_suit_range_simple(monkeypatch):
    # Prepare answers the wizard will "read" from input()
    responses: List[str] = [
        "0",  # min_cards
        "13",  # max_cards
        "0",  # min_hcp
        "10",  # max_hcp
    ]

    def fake_input(prompt: str) -> str:
        # Pop from the front of responses each time input() is called
        return responses.pop(0)

    # Replace builtins.input with our fake_input
    monkeypatch.setattr(builtins, "input", fake_input)

    result = _build_suit_range_for_prompt("Spades")

    assert isinstance(result, SuitRange)
    assert result.min_cards == 0
    assert result.max_cards == 13
    assert result.min_hcp == 0
    assert result.max_hcp == 10
