# file: tests/test_deal_generator.py

import sys
from pathlib import Path

# Ensure project root (Exec) is on sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bridge_engine.setup_env import run_setup
from bridge_engine.deal_generator import generate_deals


class DummyProfile:
    """Minimal placeholder for a profile object."""
    pass


def test_generate_deals_count_and_board_numbers(tmp_path: Path) -> None:
    base_dir = tmp_path / "out"
    setup = run_setup(
        base_dir=base_dir,
        owner="Lee",
        profile_name="TestProfile",
        ask_seed_choice=False,   # force seeded default, no prompt
    )

    profile = DummyProfile()
    num_deals = 3

    deal_set = generate_deals(setup, profile, num_deals)

    assert len(deal_set.deals) == num_deals
    assert [d.board_number for d in deal_set.deals] == [1, 2, 3]