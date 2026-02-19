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
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from .menu_help import get_menu_help
from .setup_env import run_setup, SetupError, SetupResult
from .hand_profile import HandProfile, ProfileError, validate_profile
from .deal_generator import DealSet, DealGenerationError, generate_deals
from .deal_output import DealOutputSummary, OutputError, render_deals
from .cli_io import _yes_no_help
from .profile_cli import _input_int

from . import profile_cli
from . import profile_store
from . import lin_tools
from . import profile_diagnostic
from .profile_store import PROFILE_DIR_NAME


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
        # Skip draft *_TEST.json files — they shouldn't appear in session picker
        if profile_store.is_draft_path(path):
            continue
        try:
            with path.open("r", encoding="utf-8") as f:
                data: Dict[str, Any] = json.load(f)
            profile = HandProfile.from_dict(data)
            results.append((path, profile))
        except (json.JSONDecodeError, TypeError, KeyError, ValueError, OSError) as exc:  # pragma: no cover
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
    profile_store.print_profile_display_map(display_map)

    valid_nums = sorted(display_map)
    while True:
        raw = input("\nChoose a profile by number or press Enter to cancel: ").strip()
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
# Shared helpers for session flows
# ---------------------------------------------------------------------------


def _validate_for_session(profile: HandProfile) -> HandProfile | None:
    """
    Validate a profile before use in a session (deal generation or diagnostic).

    Returns the validated (possibly re-normalised) profile, or None on failure.
    """
    print(f"\nValidating profile '{profile.profile_name}' ...")
    try:
        profile = validate_profile(profile)
    except ProfileError as exc:
        print("\nERROR: This profile is not valid:")
        print(f"  {exc}")
        print("Please edit this profile in Profile Management and try again.")
        return None

    print("Profile OK.\n")
    return profile


def _print_session_summary(
    profile: HandProfile,
    owner: str,
    summary: DealOutputSummary,
    deal_set: DealSet,
    gen_elapsed: float,
) -> None:
    """Print the post-generation session summary."""
    print("\n=== Session complete ===")
    print(f"Profile       : {profile.profile_name}")
    print(f"Owner         : {owner}")
    print(f"Deals created : {summary.num_deals}")
    print(f"Time taken    : {gen_elapsed:.1f}s")
    # Per-board timing breakdown (populated by adaptive re-seeding feature).
    # Use getattr for compatibility with test stubs / DummyDealSet objects.
    board_times = getattr(deal_set, "board_times", [])
    reseed_count = getattr(deal_set, "reseed_count", 0)
    if board_times:
        avg_time = sum(board_times) / len(board_times)
        max_time = max(board_times)
        print(f"Avg per board : {avg_time:.1f}s (max {max_time:.1f}s)")
    if reseed_count > 0:
        print(f"Re-seeds      : {reseed_count}")
    print(f"TXT output    : {summary.txt_path}")
    print(f"LIN output    : {summary.lin_path}")
    if summary.warnings:
        print("\nWarnings:")
        for w in summary.warnings:
            print(f"  - {w}")
    print("")


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

    profile = _validate_for_session(profile)
    if profile is None:
        return

    # --- Get session parameters from the user ---
    owner = _input_with_default("Owner / player name", "Lee")
    base_dir_str = _input_with_default("Base output directory (will contain txt/ and lin/)", "out")
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
    except (SetupError, OSError) as exc:  # pragma: no cover (interactive failure path)
        print(f"\nERROR running setup_env.run_setup: {exc}")
        return

    # Ask whether to use random N/S, E/W rotation for this generation.
    # Default comes from profile metadata, falling back to True.
    default_rotate = profile.rotate_deals_by_default
    rotate_deals = _yes_no_help(
        "Randomly rotate deals (swap N/S and E/W) for this generation?",
        "yn_rotate_deals",
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

    _print_session_summary(profile, owner, summary, deal_set, gen_elapsed)


# ---------------------------------------------------------------------------
# Profile Management wrapper
# ---------------------------------------------------------------------------


# Public wrapper (kept for main_menu call site)
def run_deal_generation() -> None:
    _run_deal_generation_session()


# ---------------------------------------------------------------------------
# Generic menu loop
# ---------------------------------------------------------------------------

# Each menu item is (label, handler_or_None).
# handler=None means the item is the exit/back option (always index 0).
MenuItem = Tuple[str, Optional[Callable[[], None]]]


def _run_menu_loop(
    title: str,
    items: Sequence[MenuItem],
    help_key: str,
    exit_message: str = "",
) -> None:
    """
    Generic interactive menu loop.

    items[0] is always the exit/back option (handler ignored).
    The last item is always "Help" (prints get_menu_help(help_key)).
    All other items dispatch to their handler.
    """
    max_choice = len(items) - 1

    while True:
        print(f"\n=== {title} ===")
        for idx, (label, _handler) in enumerate(items):
            print(f"{idx}) {label}")

        choice = _input_int(
            f"Choose [0-{max_choice}] [0]: ",
            default=0,
            minimum=0,
            maximum=max_choice,
            show_range_suffix=False,
        )

        if choice == 0:
            if exit_message:
                print(exit_message)
            break

        label, handler = items[choice]
        if handler is not None:
            handler()
        else:
            # Fallback: help item with no explicit handler
            print()
            print(get_menu_help(help_key))


# ---------------------------------------------------------------------------
# Main menu
# ---------------------------------------------------------------------------


def _help_main() -> None:
    print()
    print(get_menu_help("main_menu"))


def main_menu() -> None:
    """Top-level interactive menu for the Bridge Hand Generator."""
    _run_menu_loop(
        title="Bridge Hand Generator",
        items=[
            ("Exit", None),
            ("Profile management", lambda: profile_cli.run_profile_manager()),
            ("Deal generation", run_deal_generation),
            ("Admin", admin_menu),
            ("Help", _help_main),
        ],
        help_key="main_menu",
        exit_message="Exiting Bridge Hand Generator.",
    )


def _run_profile_diagnostic_interactive() -> None:
    """
    Interactive wrapper: let the user pick a profile and run the v2
    diagnostic (failure attribution, per-board results, aggregate summary).
    """
    print("\n=== Profile Diagnostic ===")

    profile = _choose_profile_for_session()
    if profile is None:
        return

    profile = _validate_for_session(profile)
    if profile is None:
        return

    num_boards = _input_int_with_default("Number of boards to diagnose", 20, minimum=1)

    profile_diagnostic.run_profile_diagnostic(
        profile=profile,
        num_boards=num_boards,
    )


def _help_admin() -> None:
    print()
    print(get_menu_help("admin_menu"))


def admin_menu() -> None:
    """Admin / tools submenu (LIN combiner, draft tools, diagnostics, etc.)."""
    _run_menu_loop(
        title="Bridge Hand Generator – Admin",
        items=[
            ("Exit", None),
            ("LIN Combiner", lin_tools.combine_lin_files_interactive),
            ("Recover/Delete *_TEST.json drafts", profile_cli.run_draft_tools),
            ("Profile Diagnostic", _run_profile_diagnostic_interactive),
            ("Help", _help_admin),
        ],
        help_key="admin_menu",
    )


def main() -> None:
    """
    Public entrypoint for interactive CLI.

    Always launches the full main menu (with LIN tools).
    """
    main_menu()


if __name__ == "__main__":
    main()
