# tests/test_setup_env.py
from __future__ import annotations

from pathlib import Path

from bridge_engine.setup_env import run_setup, DEFAULT_SEED, SetupResult


def test_run_setup_seeded_default(tmp_path: Path) -> None:
    base_dir = tmp_path / "out"
    owner = "Lee Guy"
    profile_name = "WeakTwo"

    setup = run_setup(
        base_dir=base_dir,
        owner=owner,
        profile_name=profile_name,
        ask_seed_choice=False,
        use_seeded_default=True,
    )

    # seeded mode by default
    assert setup.use_seeded_run is True
    assert setup.seed == DEFAULT_SEED

    # directory structure
    assert setup.base_dir == base_dir.resolve()
    assert setup.txt_dir == setup.base_dir / "txt"
    assert setup.lin_dir == setup.base_dir / "lin"
    assert setup.log_dir == setup.base_dir / "logs"

    assert setup.txt_dir.is_dir()
    assert setup.lin_dir.is_dir()
    assert setup.log_dir.is_dir()

    # output files are placed correctly
    assert setup.output_txt_file.parent == setup.txt_dir
    assert setup.output_lin_file.parent == setup.lin_dir

    # filenames are correct pattern:
    # Lee_Guy_WeakTwo_{MMDD_HHMM}.txt
    # Lee_Guy_WeakTwo_BBO_{MMDD_HHMM}.lin
    assert setup.output_txt_file.name.startswith("Lee_Guy_WeakTwo_")
    assert setup.output_txt_file.suffix == ".txt"

    assert setup.output_lin_file.name.startswith("Lee_Guy_WeakTwo_BBO_")
    assert setup.output_lin_file.suffix == ".lin"


def test_run_setup_random_non_interactive(tmp_path: Path) -> None:
    base_dir = tmp_path / "out"

    setup = run_setup(
        base_dir=base_dir,
        owner="Lee Guy",
        profile_name="RandomNonInteractive",
        ask_seed_choice=False,
        use_seeded_default=False,
    )

    assert setup.use_seeded_run is False
    assert setup.seed != DEFAULT_SEED  # random seed chosen
    assert isinstance(setup.seed, int)


def test_run_setup_creates_nested_directories(tmp_path: Path) -> None:
    base_dir = tmp_path / "a" / "b" / "c"

    setup = run_setup(
        base_dir=base_dir,
        owner="Lee Guy",
        profile_name="NestedDirTest",
        ask_seed_choice=False,
        use_seeded_default=True,
    )

    assert setup.base_dir == base_dir.resolve()
    assert setup.txt_dir.is_dir()
    assert setup.lin_dir.is_dir()
    assert setup.log_dir.is_dir()


def test_owner_is_normalised_in_filenames(tmp_path: Path) -> None:
    base_dir = tmp_path / "out"

    setup = run_setup(
        base_dir=base_dir,
        owner="  Lee Guy  ",  # note spaces
        profile_name="ProfileX",
        ask_seed_choice=False,
        use_seeded_default=True,
    )

    # Human-readable owner is preserved
    assert setup.owner == "  Lee Guy  "

    # Filename-safe owner is normalised
    assert setup.owner_file == "Lee_Guy"

    # Filenames use normalised owner
    assert setup.output_txt_file.name.startswith("Lee_Guy_ProfileX_")
    assert setup.output_lin_file.name.startswith("Lee_Guy_ProfileX_BBO_")
