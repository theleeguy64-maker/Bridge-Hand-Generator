"""
Section A – Environment Setup

This module prepares the directory structure and output filenames for a deal
generation run. It does NOT generate deals — it only:

    • Creates /txt, /lin, /logs folders under the chosen base_dir
    • Determines the output filenames for the run
    • Normalises owner for filenames (spaces → underscores) but preserves
      the original owner string in the SetupResult
    • Applies seeded or random seed logic
    • Returns a SetupResult object consumed by Section C

This version (v3) reflects the updated project architecture (Nov 2025).
"""

from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Tuple
from datetime import datetime
import random
from . import cli_prompts

DEFAULT_SEED = 778899  # canonical project-wide deterministic default seed


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class SetupError(Exception):
    """Raised when the environment cannot be prepared."""


# ---------------------------------------------------------------------------
# Data class returned by run_setup()
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SetupResult:
    """
    Canonical output from Section A.

    This object must be passed intact to Section C without modification.
    """

    # Directory roots
    base_dir: Path
    txt_dir: Path
    lin_dir: Path
    log_dir: Path

    # Output files (fully resolved paths)
    output_txt_file: Path
    output_lin_file: Path

    # Metadata for logging and Section C reproducibility
    owner: str  # preserved human-readable owner
    owner_file: str  # filename-safe version (spaces collapsed)
    profile_name: str  # profile ID/name from user
    timestamp: str  # MMDD_HHMM
    seed: int  # actual seed used
    use_seeded_run: bool  # True = default seed, False = random seed


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _normalise_owner_for_filename(owner: str) -> str:
    """
    Convert any owner string to underscore-separated filename-safe form.
    E.g. "  Lee Guy  " → "Lee_Guy"
    """
    owner_clean = owner.strip()
    parts = owner_clean.split()
    return "_".join(parts)


def _timestamp_now() -> str:
    """
    Return timestamp string used for filenames.
    Format: MMDD_HHMM (e.g. 1119_1327)
    """
    return datetime.now().strftime("%m%d_%H%M")


def _ensure_directories(base_dir: Path) -> Tuple[Path, Path, Path]:
    """
    Create base_dir and the three subdirectories:
        txt/
        lin/
        logs/
    """
    try:
        base_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise SetupError(f"Could not create base directory {base_dir}: {exc}")

    txt = base_dir / "txt"
    lin = base_dir / "lin"
    logs = base_dir / "logs"

    for d in (txt, lin, logs):
        try:
            d.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise SetupError(f"Could not create directory {d}: {exc}")

    return txt, lin, logs


# ---------------------------------------------------------------------------
# Main entry point for Section A
# ---------------------------------------------------------------------------


def run_setup(
    *,
    base_dir: Path,
    owner: str,
    profile_name: str,
    ask_seed_choice: bool = False,
    use_seeded_default: bool = True,
) -> SetupResult:
    """
    Prepare directories + filenames + seed for this run.

    Parameters
    ----------
    base_dir : Path
        Parent directory under which txt/, lin/, logs/ will be created.

    owner : str
        Name of the person generating deals. Used for filenames (collapsed)
        and preserved verbatim in SetupResult.

    profile_name : str
        Profile ID/name (e.g. "WeakTwo", "Cappelletti", etc.)

    ask_seed_choice : bool
        If True, interactively ask the user:
            "Use default seed?"
        If False, follow use_seeded_default.

    use_seeded_default : bool
        If ask_seed_choice == False:
            True  → use DEFAULT_SEED
            False → use random seed

    Behaviour
    ---------
    • Always uses DEFAULT_SEED unless the user explicitly chooses random.
    • Tests and logs always use default seed (via ask_seed_choice=False).
    • Creates /txt, /lin, /logs under base_dir.
    • Builds canonical filenames:
          {OwnerFile}_{Profile}_{MMDD_HHMM}.txt
          {OwnerFile}_{Profile}_BBO_{MMDD_HHMM}.lin
    • Returns SetupResult with fully resolved paths.

    Returns
    -------
    SetupResult
    """
    # Normalise & preserve owner
    owner_preserved = owner
    owner_file = _normalise_owner_for_filename(owner)

    # Determine whether to use the default deterministic seed or a random one.
    if ask_seed_choice:
        use_seeded = cli_prompts.prompt_yes_no(
            "Use default seeded run?",
            default=True,
        )
    else:
        use_seeded = use_seeded_default

    if use_seeded:
        seed = DEFAULT_SEED
        seeded_flag = True
    else:
        seed = random.randint(1, 2**31 - 1)
        seeded_flag = False

    # Apply seed
    random.seed(seed)

    # Create directories
    txt_dir, lin_dir, log_dir = _ensure_directories(base_dir)

    # Timestamp
    ts = _timestamp_now()

    # Filenames
    txt_file = txt_dir / f"{owner_file}_{profile_name}_{ts}.txt"
    lin_file = lin_dir / f"{owner_file}_{profile_name}_BBO_{ts}.lin"

    # Build result
    return SetupResult(
        base_dir=base_dir.resolve(),
        txt_dir=txt_dir.resolve(),
        lin_dir=lin_dir.resolve(),
        log_dir=log_dir.resolve(),
        output_txt_file=txt_file.resolve(),
        output_lin_file=lin_file.resolve(),
        owner=owner_preserved,
        owner_file=owner_file,
        profile_name=profile_name,
        timestamp=ts,
        seed=seed,
        use_seeded_run=seeded_flag,
    )
