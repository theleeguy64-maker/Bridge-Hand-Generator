"""
High-level Orchestrator for the Bridge Hand Generator.

This module provides a top-level CLI that ties together:

- Section A: Environment setup (setup_env.run_setup)
- Section B: Profile management (profile_cli.main)
- Section C: Deal generation (deal_generator.generate_deals)
- Section D: Output (deal_output.render_deals)

It implements:

  • A main menu:
        1) Profile management
        2) Deal generation
        3) LIN tools - Combine LIN files
        4) Exit

  • "Session bundles" for deal generation:
        - User picks a saved profile from disk
        - Profile is validated before use
        - User chooses owner, base output directory, and number of deals
        - Section A, C, and D are run in sequence
        - A clear summary of the run is printed

  • Validation integration:
        - Before generating any deals, validate_profile(profile) is called
        - If invalid, we show a clear message and return to the main menu
"""

from __future__ import annotations

import json
import sys
import time

from pathlib import Path
from typing import Any, Dict, List, Tuple

from .menu_help import get_menu_help
from .setup_env import run_setup, SetupResult
from .hand_profile import HandProfile, ProfileError, validate_profile
from .deal_generator import DealSet, DealGenerationError, generate_deals
from .deal_output import DealOutputSummary, OutputError, render_deals
from .profile_cli import _input_int

from . import profile_cli
from . import profile_store
from . import lin_tools
from . import profile_diagnostic


# Directory where JSON profiles live (relative to project root / CWD)
PROFILE_DIR_NAME = "profiles"


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def _input_with_default(prompt: str, default: str) -> str:
    """
    Prompt the user with a default value.

    Example:
        name = _input_with_default("Owner name", "Lee")
    """
    full_prompt = f"{prompt} [{default}]: "
    response = input(full_prompt).strip()
    if not response:
        return default
    return response


def _input_int_with_default(prompt: str, default: int, minimum: int = 1) -> int:
    """
    Prompt for an integer with a default and simple validation.
    """
    while True:
        full_prompt = f"{prompt} [{default}]: "
        raw = input(full_prompt).strip()
        if not raw:
            value = default
        else:
            try:
                value = int(raw)
            except ValueError:
                print("Please enter a whole number.")
                continue

        if value < minimum:
            print(f"Please enter a value >= {minimum}.")
            continue
        return value


def _yes_no(prompt: str, default: bool = True) -> bool:
    """
    Simple Yes/No prompt.

    default=True  -> [Y/n]
    default=False -> [y/N]
    """
    if default:
        suffix = " [Y/n]: "
    else:
        suffix = " [y/N]: "

    while True:
        ans = input(prompt + suffix).strip().lower()
        if not ans:
            return default
        if ans in ("y", "yes"):
            return True
        if ans in ("n", "no"):
            return False
        print("Please answer 'y' or 'n'.")


# ---------------------------------------------------------------------------
# Profile discovery / selection for deal generation (Session bundles)
# ---------------------------------------------------------------------------


def _profiles_dir(base_dir: Path | None = None) -> Path:
    """
    Resolve the directory where profiles are stored.
    """
    if base_dir is None:
        base_dir = Path.cwd()
    return base_dir / PROFILE_DIR_NAME


def _discover_profiles(base_dir: Path | None = None) -> List[Tuple[Path, HandProfile]]:
    """
    Scan the profiles directory for JSON profiles and load them as HandProfile
    objects.

    Any file that fails to load cleanly is skipped with a warning.
    """
    dir_path = _profiles_dir(base_dir)
    results: List[Tuple[Path, HandProfile]] = []

    if not dir_path.is_dir():
        return results

    for path in sorted(dir_path.glob("*.json")):
        try:
            with path.open("r", encoding="utf-8") as f:
                data: Dict[str, Any] = json.load(f)
            profile = HandProfile.from_dict(data)
            results.append((path, profile))
        except Exception as exc:  # pragma: no cover  (used only in CLI)
            print(
                f"WARNING: Failed to load profile from {path}: {exc}",
                file=sys.stderr,
            )
    return results


def _choose_profile_for_session() -> HandProfile | None:
    """
    Interactively let the user choose a profile from disk for a deal-generation
    session.

    Returns
    -------
    HandProfile or None
        The selected profile, or None if the user cancels or no profiles exist.
    """
    profiles = _discover_profiles()
    if not profiles:
        print("No profiles found. Please create one in Profile Management first.")
        return None

    display_map = profile_store.build_profile_display_map(profiles)

    print("\nAvailable profiles on disk:")
    for num in sorted(display_map):
        _, profile = display_map[num]
        tag = getattr(profile, "tag", "Unknown")
        dealer = getattr(profile, "dealer", "?")
        version = getattr(profile, "version", "")
        version_str = f"v{version}" if version else "(no version)"
        print(f"  {num}) {profile.profile_name} ({version_str}, tag={tag}, dealer={dealer})")

    valid_nums = sorted(display_map)
    while True:
        raw = input(
            f"\nChoose a profile by number "
            "or press Enter to cancel: "
        ).strip()
        if not raw:
            print("Cancelled profile selection.")
            return None
        try:
            choice = int(raw)
        except ValueError:
            print("Please enter a number.")
            continue

        if choice in display_map:
            _, profile = display_map[choice]
            return profile

        print(f"Invalid choice. Valid numbers: {valid_nums}")


# ---------------------------------------------------------------------------
# Deal generation session (ties together A, B, C, D)
# ---------------------------------------------------------------------------


def _run_deal_generation_session() -> None:
    """
    Run a full "session bundle" for deal generation:

    1) Let the user choose a profile from disk.
    2) Validate the profile (Section B validation).
    3) Ask for owner name, base output directory, and number of deals.
    4) Call Section A (run_setup) to prepare output paths and seed.
    5) Call Section C (generate_deals) to generate deals.
    6) Call Section D (render_deals) to write TXT and LIN.
    7) Print a summary of the session.
    """
    print("\n=== Deal Generation Session ===")

    profile = _choose_profile_for_session()
    if profile is None:
        return

    # --- Validate the profile before doing any work (Section B integration) ---
    print(f"\nValidating profile '{profile.profile_name}' ...")
    try:
        # validate_profile may return a new (round-tripped) instance;
        # use that, so any normalisation is applied.
        profile = validate_profile(profile)
    except ProfileError as exc:
        print("\nERROR: This profile is not valid:")
        print(f"  {exc}")
        print("Please edit this profile in Profile Management and try again.")
        return

    print("Profile OK.\n")

    # --- Get session parameters from the user ---
    owner = _input_with_default("Owner / player name", "Lee")
    base_dir_str = _input_with_default(
        "Base output directory (will contain txt/ and lin/)", "out"
    )
    base_dir = Path(base_dir_str).expanduser().resolve()
    num_deals = _input_int_with_default("Number of deals to generate", 6, minimum=1)

    print("\nSection A: environment setup")
    print(f"  Base dir: {base_dir}")
    print(f"  Profile : {profile.profile_name}")
    print(f"  Owner   : {owner}")

    # For now, we let setup_env handle the seeded/random choice interactively
    # via ask_seed_choice=True.
    try:
        setup: SetupResult = run_setup(
            base_dir=base_dir,
            owner=owner,
            profile_name=profile.profile_name,
            ask_seed_choice=True,
        )
    except Exception as exc:  # pragma: no cover (interactive failure path)
        print(f"\nERROR running setup_env.run_setup: {exc}")
        return

    # Ask whether to use random N/S, E/W rotation for this generation.
    # Default comes from profile metadata, falling back to True.
    default_rotate = getattr(profile, "rotate_deals_by_default", True)
    rotate_deals = _yes_no(
        "Randomly rotate deals (swap N/S and E/W) for this generation?",
        default_rotate,
    )

    # --- Section C: deal generation ---
    print("\nSection C: generating deals ...")
    gen_start = time.monotonic()
    try:
        deal_set: DealSet = generate_deals(
            setup=setup,
            profile=profile,
            num_deals=num_deals,
            enable_rotation=rotate_deals,
        )
    except DealGenerationError as exc:
        print(f"\nERROR during deal generation: {exc}")
        return
    gen_elapsed = time.monotonic() - gen_start

    # --- Section D: output ---
    print("\nSection D: writing outputs ...")
    try:
        summary: DealOutputSummary = render_deals(
            setup=setup,
            profile=profile,
            deal_set=deal_set,
            print_to_console=True,
            append_txt=False,
        )
    except OutputError as exc:
        print(f"\nERROR while rendering deals: {exc}")
        return

    # --- Session summary ---
    print("\n=== Session complete ===")
    print(f"Profile       : {profile.profile_name}")
    print(f"Owner         : {owner}")
    print(f"Deals created : {summary.num_deals}")
    print(f"Time taken    : {gen_elapsed:.1f}s")
    # Per-board timing breakdown (populated by adaptive re-seeding feature).
    # Use getattr for compatibility with test stubs / DummyDealSet objects.
    _board_times = getattr(deal_set, "board_times", [])
    _reseed_count = getattr(deal_set, "reseed_count", 0)
    if _board_times:
        avg_time = sum(_board_times) / len(_board_times)
        max_time = max(_board_times)
        print(f"Avg per board : {avg_time:.1f}s (max {max_time:.1f}s)")
    if _reseed_count > 0:
        print(f"Re-seeds      : {_reseed_count}")
    print(f"TXT output    : {summary.txt_path}")
    print(f"LIN output    : {summary.lin_path}")
    if summary.warnings:
        print("\nWarnings:")
        for w in summary.warnings:
            print(f"  - {w}")
    print("")


# ---------------------------------------------------------------------------
# Profile Management wrapper
# ---------------------------------------------------------------------------


def _run_profile_management() -> None:
    """Launch the Profile Manager UI."""
    profile_cli.run_profile_manager()


# Public wrapper (kept for main_menu call site)
def run_deal_generation() -> None:
    _run_deal_generation_session()

# ---------------------------------------------------------------------------
# Main menu
# ---------------------------------------------------------------------------

def main_menu() -> None:
    """
    Top-level interactive menu for the Bridge Hand Generator.
    """
    while True:
        print("\n=== Bridge Hand Generator ===")
        print("0) Exit")
        print("1) Profile management")
        print("2) Deal generation")
        print("3) Admin")
        print("4) Help")

        choice = _input_int(
            "Choose [0-4] [0]: ",
            default=0,
            minimum=0,
            maximum=4,
            show_range_suffix=False,
        )

        if choice == 0:
            print("Exiting Bridge Hand Generator.")
            break

        elif choice == 1:
            # Profile Manager
            from . import profile_cli
            profile_cli.run_profile_manager()

        elif choice == 2:
            # Deal generation main flow (legacy name kept for now)
            run_deal_generation()

        elif choice == 3:
            # Admin submenu
            admin_menu()

        elif choice == 4:
            # Main menu help
            print()
            print(get_menu_help("main_menu"))
            

def _run_profile_diagnostic_interactive() -> None:
    """
    Interactive wrapper: let the user pick a profile and run the v2
    diagnostic (failure attribution, per-board results, aggregate summary).
    """
    print("\n=== Profile Diagnostic ===")

    profile = _choose_profile_for_session()
    if profile is None:
        return

    # Validate the profile before running the diagnostic.
    print(f"\nValidating profile '{profile.profile_name}' ...")
    try:
        profile = validate_profile(profile)
    except ProfileError as exc:
        print(f"\nERROR: This profile is not valid:\n  {exc}")
        print("Please edit this profile in Profile Management and try again.")
        return
    print("Profile OK.\n")

    num_boards = _input_int_with_default(
        "Number of boards to diagnose", 20, minimum=1
    )

    profile_diagnostic.run_profile_diagnostic(
        profile=profile,
        num_boards=num_boards,
    )


def admin_menu() -> None:
    """
    Admin / tools submenu (LIN combiner, draft tools, diagnostics, etc.).
    """
    while True:
        print("\n=== Bridge Hand Generator – Admin ===")
        print("0) Exit")
        print("1) LIN Combiner")
        print("2) Recover/Delete *_TEST.json drafts")
        print("3) Profile Diagnostic")
        print("4) Help")

        choice = _input_int(
            "Choose [0-4] [0]: ",
            default=0,
            minimum=0,
            maximum=4,
            show_range_suffix=False,
        )

        if choice == 0:
            break

        elif choice == 1:
            lin_tools.combine_lin_files_interactive()

        elif choice == 2:
            profile_cli.run_draft_tools()

        elif choice == 3:
            _run_profile_diagnostic_interactive()

        elif choice == 4:
            print()
            print(get_menu_help("admin_menu"))            



def main() -> None:
    """
    Public entrypoint for interactive CLI.

    Always launches the full main menu (with LIN tools).
    """
    main_menu()


if __name__ == "__main__":
    main()
    