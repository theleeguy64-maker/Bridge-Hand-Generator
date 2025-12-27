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
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .setup_env import run_setup, SetupResult
from .hand_profile import HandProfile, ProfileError, validate_profile
from .deal_generator import DealSet, DealGenerationError, generate_deals
from .deal_output import DealOutputSummary, OutputError, render_deals
from . import profile_cli
from . import lin_tools

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

    print("\nAvailable profiles on disk:")
    for idx, (path, profile) in enumerate(profiles, start=1):
        tag = getattr(profile, "tag", "Unknown")
        dealer = getattr(profile, "dealer", "?")
        version = getattr(profile, "version", "")
        version_str = f"v{version}" if version else "(no version)"
        print(f"  {idx}) {profile.profile_name} ({version_str}, tag={tag}, dealer={dealer})")
        print(f"      File: {path.name}")

    while True:
        raw = input(
            f"\nChoose a profile by number [1-{len(profiles)}] "
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

        if 1 <= choice <= len(profiles):
            _, profile = profiles[choice - 1]
            return profile

        print(f"Please choose a number between 1 and {len(profiles)}.")


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
    """
    Launch the Profile Manager UI.

    We prefer profile_cli.run_profile_manager() if available, and fall
    back to profile_cli.main(). This avoids spurious "main() is not
    defined" errors when the module layout changes.
    """
    try:
        from bridge_engine import profile_cli  # type: ignore[import]
    except Exception as exc:  # pragma: no cover (should not happen in normal runs)
        print("ERROR: Could not import profile_cli:", exc)
        return

    # Preferred entrypoint.
    if hasattr(profile_cli, "run_profile_manager"):
        profile_cli.run_profile_manager()  # type: ignore[attr-defined]
        return

    # Backwards-compatible entrypoint.
    if hasattr(profile_cli, "main"):
        profile_cli.main()  # type: ignore[attr-defined]
        return

    # If we get here, something is genuinely wrong with the module.
    print(
        "ERROR: profile_cli.run_profile_manager() / profile_cli.main() "
        "is not defined. Please ensure profile_cli.py has an entrypoint."
    )


# Public wrappers (kept for any external callers)
def run_deal_generation() -> None:
    _run_deal_generation_session()

def _print_main_menu(include_lin: bool) -> None:
    """
    Helper to print the main menu.

    include_lin=False → legacy 3-option menu (used by tests via _main_menu)
    include_lin=True  → full 4-option menu with LIN tools.
    """
    print()
    print("=== Bridge Hand Generator ===")
    print("1) Profile management")
    print("2) Deal generation")
    if include_lin:
        print("3) LIN tools - Combine LIN files")
        print("4) Exit")
    else:
        print("3) Exit")

def run_profile_menu() -> None:
    _run_profile_management()

# ---------------------------------------------------------------------------
# Main menus
# ---------------------------------------------------------------------------

def main_menu() -> None:
    """
    Primary interactive menu used when running this module as a script.

    Includes the LIN tools option.
    """
    while True:
        print()
        print("=== Bridge Hand Generator ===")
        print("1) Profile management")
        print("2) Deal generation")
        print("3) LIN tools - Combine LIN files")
        print("4) Exit")

        choice = input("Choose [1-4] [4]: ").strip() or "4"

        if choice == "1":
            _run_profile_management()
        elif choice == "2":
            _run_deal_generation_session()
        elif choice == "3":
            lin_tools.run_lin_combiner()
        elif choice == "4":
            print("Goodbye.")
            break
        else:
            print("Invalid choice, please try again.")

def _main_menu() -> None:
    """
    Legacy main menu used by tests.

    Historically, this menu had only three options and exited on '3'.
    The tests still call _main_menu() and expect that behaviour, so we
    keep this thin wrapper separate from the real main_menu().
    """
    while True:
        print("=== Bridge Hand Generator ===")
        print("1) Profile management")
        print("2) Deal generation")
        print("3) Exit")

        choice = input("Choose [1-3]: ").strip() or "3"

        if choice == "1":
            _run_profile_management()
        elif choice == "2":
            _run_deal_generation_session()
        elif choice == "3":
            print("Goodbye.")
            break
        else:
            print("Invalid choice, please try again.")

if __name__ == "__main__":  # pragma: no cover
    main_menu()