"""
Small debug harness for NS driver/follower behaviour and sub-profile usage.

Usage (from project root):

    (.venv) python -m scripts.debug_ns_roles profiles/SomeProfile.json 200

This will:
  - load the profile
  - run N deals through the normal generator
  - print how often each ns_role_mode outcome occurred (driver seat)
  - show how often each NS sub-profile index was chosen
  - show whether index-matching appears to be happening for N/S.
"""

from __future__ import annotations

import json
import random
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Tuple

from bridge_engine.deal_generator import _build_single_constrained_deal  # type: ignore[import]
from bridge_engine.hand_profile_model import HandProfile, SeatProfile, SubProfile  # type: ignore[import]
from bridge_engine.hand_profile_validate import validate_profile  # type: ignore[import]


Seat = str  # "N", "E", "S", "W"


def _load_profile(path: Path) -> HandProfile:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return validate_profile(raw)


def _find_ns_subprofile_indices_for_board(
    profile: HandProfile,
    deal,
) -> Tuple[int | None, int | None]:
    """
    Best-effort inspection of which sub-profile index was used for N and S
    on a given deal.

    Right now the generator doesn’t expose the chosen indices directly,
    so this is heuristic: we re-run the NS sub-profile selection logic
    using the same RNG seed pattern that _build_single_constrained_deal
    uses for the board. If that ever changes, this helper will need to
    be updated.
    """
    # NOTE: This is deliberately simple for now – we just return None/None
    # and rely on future enhancements if we want precise index tracking
    # wired into the Deal object itself.
    return None, None


def main(argv: List[str]) -> int:
    if not (1 <= len(argv) <= 2):
        print("Usage: python -m scripts.debug_ns_roles PROFILE_JSON [NUM_DEALS]")
        return 1

    profile_path = Path(argv[0])
    num_deals = int(argv[1]) if len(argv) == 2 else 200

    if not profile_path.exists():
        print(f"Profile file not found: {profile_path}")
        return 1

    profile = _load_profile(profile_path)

    rng = random.Random(123456)
    ns_driver_counter: Counter[str] = Counter()
    ns_role_mode = getattr(profile, "ns_role_mode", "north_drives")

    print(f"Profile: {profile.profile_name}")
    print(f"ns_role_mode: {ns_role_mode}")
    print(f"Dealing order: {profile.hand_dealing_order}")
    print()

    # These are just placeholders for now, pending full index tracking.
    n_index_counter: Counter[int] = Counter()
    s_index_counter: Counter[int] = Counter()

    for board in range(1, num_deals + 1):
        deal = _build_single_constrained_deal(rng, profile, board_number=board)

        # Ask the profile which seat is *preferred* driver (metadata level).
        driver = profile.ns_driver_seat(rng)
        if driver is None:
            ns_driver_counter["None"] += 1
        else:
            ns_driver_counter[driver] += 1

        # Optional future: track sub-profile indices here if we expose them.
        n_idx, s_idx = _find_ns_subprofile_indices_for_board(profile, deal)
        if n_idx is not None:
            n_index_counter[n_idx] += 1
        if s_idx is not None:
            s_index_counter[s_idx] += 1

    print("NS driver seat (metadata ns_driver_seat) frequencies:")
    for key in sorted(ns_driver_counter.keys()):
        print(f"  {key}: {ns_driver_counter[key]} / {num_deals}")

    if n_index_counter or s_index_counter:
        print("\nApproximate NS sub-profile index usage (heuristic):")
        if n_index_counter:
            print("  North indices:")
            for idx in sorted(n_index_counter.keys()):
                print(f"    {idx}: {n_index_counter[idx]} / {num_deals}")
        if s_index_counter:
            print("  South indices:")
            for idx in sorted(s_index_counter.keys()):
                print(f"    {idx}: {s_index_counter[idx]} / {num_deals}")
    else:
        print("\nSub-profile index tracking is not wired yet;")
        print("this harness currently only reports ns_driver_seat frequencies.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))