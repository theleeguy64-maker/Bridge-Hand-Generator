# file: tests/test_deal_output.py

import sys
from pathlib import Path

# Ensure project root (Exec) is on sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bridge_engine.deal_output import render_deals
from bridge_engine.deal_generator import Deal, DealSet


class SetupStub:
    """
    Minimal stub that provides the attributes used by render_deals:
    - output_txt_file
    - output_lin_file
    """
    def __init__(self, txt_path: Path, lin_path: Path) -> None:
        self.output_txt_file = txt_path
        self.output_lin_file = lin_path


class DummyProfile:
    """Minimal profile stub with required attributes for deal output."""
    profile_name = "TestProfile"
    tag = "TestTag"
    author = "TestAuthor"
    version = "0.1"


def test_render_deals_creates_files(tmp_path: Path) -> None:
    txt_path = tmp_path / "out.txt"
    lin_path = tmp_path / "out.lin"

    setup = SetupStub(txt_path, lin_path)
    profile = DummyProfile()

    # Build one valid deal with 52 cards (13 per seat)
    north = [r + "S" for r in "AKQJT98765432"]
    east = [r + "H" for r in "AKQJT98765432"]
    south = [r + "D" for r in "AKQJT98765432"]
    west = [r + "C" for r in "AKQJT98765432"]

    deal = Deal(
        board_number=1,
        dealer="N",
        vulnerability="None",
        hands={
            "N": north,
            "E": east,
            "S": south,
            "W": west,
        },
    )

    deal_set = DealSet(deals=[deal])

    # This should:
    # - print to console
    # - append to txt_path
    # - append to lin_path
    render_deals(setup, profile, deal_set)

    # Text file created and contains "Board 1"
    assert txt_path.exists()
    txt_content = txt_path.read_text(encoding="utf-8")
    assert "Board 1" in txt_content

    # LIN file created and contains "qx|o1|md|1"
    assert lin_path.exists()
    lin_content = lin_path.read_text(encoding="utf-8")
    assert "qx|o1|md|3" in lin_content