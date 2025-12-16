# file: tests/test_lin_encoder.py

import sys
from pathlib import Path

# Ensure project root (Exec) is on sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bridge_engine.lin_encoder import Deal, encode_deal_to_lin_line


def test_encode_deal_to_lin_line_basic() -> None:
    # N: all spades, E: all hearts, S: all diamonds, W: all clubs
    north = [r + "S" for r in "AKQJT98765432"]
    east = [r + "H" for r in "AKQJT98765432"]
    south = [r + "D" for r in "AKQJT98765432"]
    west = [r + "C" for r in "AKQJT98765432"]

    deal = Deal(
        board_number=1,
        dealer="N",
        hands={
            "N": north,
            "E": east,
            "S": south,
            "W": west,
        },
    )

    line = encode_deal_to_lin_line(deal)

    # Basic BBO-style LIN structure checks
    assert line.startswith("qx|o1|md|3")
    assert "|ah|Board 1|" in line
    assert line.endswith("|sv|0|pg||")