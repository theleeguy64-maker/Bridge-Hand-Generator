# file: tests/test_text_output.py

import sys
from pathlib import Path

# Ensure project root (Exec) is on sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bridge_engine.text_output import FormattedDeal, format_deal_text


def test_format_deal_text_basic() -> None:
    deal = FormattedDeal(
        board_number=1,
        hands={
            "N": ["AS", "KS", "QS", "JS", "TS", "9S", "8S", "7S", "6S", "5S", "4S", "3S", "2S"],
            "E": ["AH"] * 13,
            "S": ["AD"] * 13,
            "W": ["AC"] * 13,
        },
        dealer="S",
        vulnerability="NS",
    )

    text = format_deal_text(deal)

    # Header present
    assert "Board 1 — Dealer: South — Vul: NS" in text

    # Compass headings present
    assert "North" in text
    assert "South" in text
    assert "West" in text
    assert "East" in text

    # Suit symbols present somewhere
    assert "♠" in text
    assert "♥" in text
    assert "♦" in text
    assert "♣" in text