# tests/test_constructive_benchmark_std_profiles.py

from pathlib import Path

import json
import os
import pytest

from bridge_engine import deal_generator as dg
from bridge_engine.hand_profile_model import HandProfile

PROFILE_DIR = Path("profiles")

PROFILE_FILES = [
    "Profile_A_Test_-_Loose_constraints_v0.1.json",
    "Profile_B_Test_-_tight_suit_constraints_v0.1.json",
    "Profile_C_Test_-_tight_points_constraints_v0.1.json",
    "Profile_D_Test_-_tight_and_suit_point_constraint_v0.1.json",
    "Profile_E_Test_-_tight_and_suit_point_constraint_plus_v0.1.json",
]


if os.environ.get("RUN_CONSTRUCTIVE_BENCHMARKS", "") != "1":
    pytest.skip(
        "Opt-in benchmark. Run with RUN_CONSTRUCTIVE_BENCHMARKS=1 pytest -q -s tests/test_constructive_benchmark_std_profiles.py",
        allow_module_level=True,
    )
    

def _load_profile_from_json(path: Path) -> HandProfile:
    data = json.loads(path.read_text(encoding="utf-8"))
    return HandProfile.from_dict(data)


def _mk_setup(tmp_path: Path, *, seed: int, profile_name: str):
    from bridge_engine.setup_env import SetupResult

    base_dir = tmp_path
    txt_dir = base_dir / "txt"
    lin_dir = base_dir / "lin"
    log_dir = base_dir / "log"
    txt_dir.mkdir(parents=True, exist_ok=True)
    lin_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    owner = "pytest"
    owner_file = base_dir / "OWNER.txt"
    owner_file.write_text(owner, encoding="utf-8")

    return SetupResult(
        base_dir=base_dir,
        txt_dir=txt_dir,
        lin_dir=lin_dir,
        log_dir=log_dir,
        output_txt_file=txt_dir / "out.txt",
        output_lin_file=lin_dir / "out.lin",
        owner=owner,
        owner_file=owner_file,
        profile_name=profile_name,
        timestamp="pytest",
        use_seeded_run=True,
        seed=seed,
    )


def _run_mode(tmp_path, profile, *, enable_v1: bool, num_boards: int, max_attempts: int, seed: int):
    # Save globals we mutate so we don't pollute other tests
    old_enable = dg.ENABLE_CONSTRUCTIVE_HELP
    old_max_attempts = dg.MAX_BOARD_ATTEMPTS
    old_hook = getattr(dg, "_DEBUG_STANDARD_CONSTRUCTIVE_USED", None)

    constructive_used = 0

    def hook(_profile, _board_number, _attempt_number, _help_seat):
        nonlocal constructive_used
        constructive_used += 1

    successes = 0
    failures = 0

    try:
        dg.ENABLE_CONSTRUCTIVE_HELP = enable_v1

        if hasattr(profile, "disable_constructive_help"):
            profile.disable_constructive_help = False

        dg.MAX_BOARD_ATTEMPTS = max_attempts
        dg._DEBUG_STANDARD_CONSTRUCTIVE_USED = hook

        setup = _mk_setup(tmp_path, seed=seed, profile_name=getattr(profile, "profile_name", "bench"))
        dg.generate_deals(setup, profile, num_deals=num_boards, enable_rotation=False)
        successes = num_boards

    except dg.DealGenerationError:
        failures = num_boards

    finally:
        # Restore globals
        dg._DEBUG_STANDARD_CONSTRUCTIVE_USED = old_hook
        dg.MAX_BOARD_ATTEMPTS = old_max_attempts
        dg.ENABLE_CONSTRUCTIVE_HELP = old_enable

    return {"successes": successes, "failures": failures, "constructive_used": constructive_used}    
    

@pytest.mark.parametrize("fname", PROFILE_FILES)
def test_benchmark_v1_on_vs_off_std_profiles(fname, capsys, tmp_path):
    path = PROFILE_DIR / fname
    if not path.exists():
        pytest.skip(f"Missing profile file: {path}")

    profile = _load_profile_from_json(path)

    NUM_BOARDS = 120
    MAX_ATTEMPTS = 500

    # two seeds for stability
    seeds = [0, 1]

    rows = []
    for enable_v1 in (False, True):
        agg = {"successes": 0, "failures": 0, "constructive_used": 0}
        for seed in seeds:
            r = _run_mode(tmp_path, profile, enable_v1=enable_v1, num_boards=NUM_BOARDS, max_attempts=MAX_ATTEMPTS, seed=seed)
            for k in agg:
                agg[k] += r[k]
        rows.append((enable_v1, agg))

    # Print a compact summary (view with `pytest -q -s`)
    out = []
    out.append(f"\nProfile: {fname}")
    for enable_v1, agg in rows:
        label = "V1_ON " if enable_v1 else "V1_OFF"
        out.append(
            f"  {label}  successes={agg['successes']}  failures={agg['failures']}  constructive_used={agg['constructive_used']}"
        )
    print("\n".join(out))

    # Weak sanity: ON should not be catastrophically worse than OFF
    off = rows[0][1]["successes"]
    on = rows[1][1]["successes"]
    assert on >= off
