"""
Interactive CLI for managing HandProfile objects (Section B).

Features:
    - List profiles (from the profiles/ directory)
    - Create new profile (full constraints)
    - View / print profile:
        * Show metadata and summary
        * Optionally print full constraints
    - Edit profile:
        * Edit metadata only
        * Edit constraints only (using current values as defaults)
    - Delete profile
    - Save profile as new version

Profiles are stored as JSON in:
    <project root> / profiles / <name>_v<version>.json

This module is designed to be invoked either directly:

    python -m bridge_engine.profile_cli

or via the orchestrator:

    python -m bridge_engine.orchestrator   # then choose "Profile management"
"""

from __future__ import annotations

import json
import os
import sys
import io
import tempfile
from dataclasses import replace

from contextlib import redirect_stdout
from pathlib import Path
from typing import List, Optional, Tuple

from .menu_help import get_menu_help
from .cli_io import _yes_no as _yes_no  # keep name for tests to monkeypatch

from .hand_profile import (
    SuitRange,
    RandomSuitConstraintData,
    PartnerContingentData,
    OpponentContingentSuitData,
    StandardSuitConstraints,
    SubProfile,
    sub_label,
    SeatProfile,
    HandProfile,
    ProfileError,
    validate_profile,
)

from .profile_wizard import (
    create_profile_interactive,
)

from . import profile_store

from .wizard_flow import edit_constraints_interactive as edit_constraints_interactive_flow
from .profile_store import PROFILE_DIR_NAME


# ---------------------------------------------------------------------------
# Basic input helpers
# ---------------------------------------------------------------------------


def _input_with_default(prompt: str, default: str = "") -> str:
    """
    Prompt the user, showing a default value in brackets if provided.
    Returns the user's input, or the default if they press Enter.
    """
    if default:
        full = f"{prompt} [{default}]: "
    else:
        full = prompt

    raw = input(full).strip()
    return raw if raw != "" else default


def prompt_choice(prompt: str, choices: List[str], default: Optional[str] = None) -> str:
    """
    Prompt the user to choose one of choices.

    choices: list of allowed upper-case strings (e.g. ["N","E","S","W"]).
    """
    choice_str = "/".join(choices)
    if default is not None:
        full = f"{prompt} ({choice_str}) (default {default}): "
    else:
        full = f"{prompt} ({choice_str}): "

    while True:
        raw = _input_with_default(full, default="")
        resp = raw.strip().upper()
        if not resp and default is not None:
            return default
        if resp in choices:
            return resp
        print(f"Please choose one of: {choice_str}")


def _input_int(
    prompt: str,
    default: int,
    minimum: int,
    maximum: int,
    *,
    show_range_suffix: bool = True,
) -> int:
    """
    Prompt for an integer with a default and a min/max range.

    If show_range_suffix is False, the prompt omits the '(>= min and <= max)'
    suffix, but the validation still enforces [minimum, maximum].
    """
    while True:
        if show_range_suffix:
            suffix = f" (>= {minimum} and <= {maximum})"
        else:
            suffix = ""

        full_prompt = f"{prompt} [{default}]{suffix}: "
        raw = input(full_prompt).strip()

        if not raw:
            value = default
        else:
            try:
                value = int(raw)
            except ValueError:
                print("Please enter a whole number.")
                continue

        if value < minimum or value > maximum:
            print(f"Please enter a value between {minimum} and {maximum}.")
            continue

        return value


def prompt_yes_no(prompt: str, default: bool = True) -> bool:
    # Important: tests monkeypatch profile_cli._yes_no
    return _yes_no(prompt, default)


# ---------------------------------------------------------------------------
# Profile JSON I/O
# ---------------------------------------------------------------------------


def _profiles_dir(base_dir: Optional[Path] = None) -> Path:
    if base_dir is None:
        base_dir = Path.cwd()
    return base_dir / PROFILE_DIR_NAME


def _safe_file_stem(name: str) -> str:
    """Normalise profile_name into a filesystem-safe stem."""
    stem = "_".join(name.strip().split())
    return stem or "Profile"


def _profile_path_for(profile: HandProfile, base_dir: Optional[Path] = None) -> Path:
    """Construct a default file path for a profile based on name and version."""
    dir_path = _profiles_dir(base_dir)
    dir_path.mkdir(parents=True, exist_ok=True)
    stem = _safe_file_stem(profile.profile_name)
    version = profile.version
    if version:
        fname = f"{stem}_v{version}.json"
    else:
        fname = f"{stem}.json"
    return dir_path / fname


def _load_profiles() -> List[Tuple[Path, HandProfile]]:
    """
    Load all JSON profiles from profiles/ directory.

    Returns a list of (path, HandProfile) for successfully loaded profiles.
    Prints warnings for any files that fail to load.
    """
    dir_path = _profiles_dir()
    results: List[Tuple[Path, HandProfile]] = []
    if not dir_path.is_dir():
        return results

    for path in sorted(dir_path.glob("*.json")):
        if profile_store.is_draft_path(path):
            continue
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            profile = HandProfile.from_dict(data)
            results.append((path, profile))
        except (json.JSONDecodeError, TypeError, KeyError, ValueError, ProfileError) as exc:
            print(
                f"WARNING: Failed to load profile from {path}: {exc}",
                file=sys.stderr,
            )
    return results


def _save_profile_to_path(profile: HandProfile, path: Path) -> None:
    """Save profile as JSON to the given path (atomic write).

    Writes to a temp file in the same directory, then renames.
    If the process dies mid-write, the original file stays intact
    (os.replace is atomic on the same filesystem).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(profile.to_dict(), indent=2, sort_keys=True) + "\n"
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp", prefix=path.stem + "_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, str(path))
    except BaseException:
        # Clean up temp file on any failure.
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# Menu actions
# ---------------------------------------------------------------------------


def _choose_profile(profiles: List[Tuple[Path, HandProfile]]) -> Optional[Tuple[Path, HandProfile]]:
    """Let user pick a profile by display number. Returns (path, profile) or None."""
    if not profiles:
        print("No profiles found.")
        return None

    display_map = profile_store.build_profile_display_map(profiles)

    print("\nView or Edit Profiles on disk:")
    profile_store.print_profile_display_map(display_map)

    valid_nums = sorted(display_map)
    choice = _input_int(
        "Choose profile number (0 to cancel)",
        default=0,
        minimum=0,
        maximum=max(valid_nums),
        show_range_suffix=False,
    )
    if choice == 0:
        return None
    if choice in display_map:
        return display_map[choice]
    print("Invalid choice.")
    return None


def list_profiles_action() -> None:
    profiles = _load_profiles()
    if not profiles:
        print("\nNo profiles created yet.")
        return

    display_map = profile_store.build_profile_display_map(profiles)

    print("\nProfiles on disk:")
    profile_store.print_profile_display_map(display_map)


def draft_tools_action() -> None:
    profiles_dir = _profiles_dir()  # or however profile_cli resolves profiles/
    drafts = profile_store.list_drafts(profiles_dir)

    if not drafts:
        print("\nNo draft *_TEST.json files found.")
        return

    print("\nDraft *_TEST.json files:")
    for i, p in enumerate(drafts, start=1):
        print(f"  {i}) {p.name}")

    while True:
        print("\nActions:")
        print("  1) Delete one draft")
        print("  2) Delete ALL drafts")
        print("  3) Cancel")
        print("  4) Help")

        action = _input_int("Choose [1-4]", default=3, minimum=1, maximum=4, show_range_suffix=False)

        if action == 4:
            print(get_menu_help("draft_tools"))
            continue

        break

    if action == 3:
        return

    if action == 2:
        if prompt_yes_no("Really delete ALL draft *_TEST.json files?", False):
            deleted = 0
            for p in drafts:
                try:
                    p.unlink()
                    deleted += 1
                except OSError as exc:
                    print(f"Failed to delete {p.name}: {exc}")
            print(f"Deleted {deleted} draft(s).")
        return

    # action == 1
    idx = _input_int(
        f"Which draft? [1-{len(drafts)}]",
        default=1,
        minimum=1,
        maximum=len(drafts),
        show_range_suffix=False,
    )
    p = drafts[idx - 1]
    if prompt_yes_no(f"Delete draft {p.name}?", False):
        try:
            p.unlink()
            print(f"Deleted {p.name}")
        except OSError as exc:
            print(f"Failed to delete {p.name}: {exc}")


def create_profile_action() -> None:
    profile = create_profile_interactive()

    print()
    print("Rotate set to Yes, NS and EW role modes set to no_driver_no_index")
    print()
    print("Metadata can be changed in 'Edit Profile'")

    if prompt_yes_no("Save this new profile?", True):
        path = _profile_path_for(profile)
        _save_profile_to_path(profile, path)
        profile_store.delete_draft_for_canonical(path)


def _print_suit_range(label: str, r: SuitRange, indent: str = "") -> None:
    print(f"{indent}{label}: cards {r.min_cards}–{r.max_cards}, HCP {r.min_hcp}–{r.max_hcp}")


def _fmt_suits(suits) -> str:
    """
    Format suits as a stable ordered list: [S,H,D,C]
    Accepts list/tuple/set or a compact string like "SH".
    """
    if suits is None:
        return "[]"
    suits_list = list(suits)

    order = ["S", "H", "D", "C"]
    suits_sorted = [s for s in order if s in set(suits_list)]
    # Fallback: if something unexpected came in, keep what we got
    if not suits_sorted:
        suits_sorted = suits_list

    return "[" + ",".join(suits_sorted) + "]"


def _print_standard_constraints(std: StandardSuitConstraints, indent: str = "") -> None:
    print(f"{indent}Total HCP: {std.total_min_hcp}–{std.total_max_hcp} (for entire hand)")
    _print_suit_range("Spades", std.spades, indent + "  ")
    _print_suit_range("Hearts", std.hearts, indent + "  ")
    _print_suit_range("Diamonds", std.diamonds, indent + "  ")
    _print_suit_range("Clubs", std.clubs, indent + "  ")


def _print_random_suit_constraint(rs: RandomSuitConstraintData, indent: str = "") -> None:
    suits_txt = _fmt_suits(rs.allowed_suits)
    req = rs.required_suits_count

    print(f"{indent}Random Suit: {req} of {suits_txt} must meet:")
    for idx, r in enumerate(rs.suit_ranges, start=1):
        print(f"{indent}  #{idx}: cards {r.min_cards}–{r.max_cards}, HCP {r.min_hcp}–{r.max_hcp}")

    if rs.pair_overrides:
        print(f"{indent}  When specific suit pairs are chosen, override ranges:")
        for o in rs.pair_overrides:
            suits = o.suits
            first_range = o.first_range
            second_range = o.second_range

            # Name each suit explicitly instead of "first"/"second"
            suit_names = {
                "S": "Spades",
                "H": "Hearts",
                "D": "Diamonds",
                "C": "Clubs",
            }
            # SuitPairOverride guarantees exactly 2 suits and non-None ranges.
            s1 = suit_names.get(suits[0], suits[0])
            s2 = suit_names.get(suits[1], suits[1])

            parts: List[str] = [
                f"{s1}: cards {first_range.min_cards}–{first_range.max_cards}, "
                f"HCP {first_range.min_hcp}–{first_range.max_hcp}",
                f"{s2}: cards {second_range.min_cards}–{second_range.max_cards}, "
                f"HCP {second_range.min_hcp}–{second_range.max_hcp}",
            ]

            print(f"{indent}    If {_fmt_suits(suits)}: " + "; ".join(parts))


def _print_partner_contingent_constraint(pc: PartnerContingentData, indent: str = "") -> None:
    print(f"{indent}Partner Contingent constraint:")
    print(f"{indent}  Partner seat: {pc.partner_seat}")
    if pc.use_non_chosen_suit:
        print(f"{indent}  Target: partner's UNCHOSEN suit")
    else:
        print(f"{indent}  Target: partner's CHOSEN suit")
    _print_suit_range("Suit", pc.suit_range, indent + "  ")


def _print_opponent_contingent_constraint(oc: OpponentContingentSuitData, indent: str = "") -> None:
    print(f"{indent}Opponent Contingent-Suit constraint:")
    print(f"{indent}  Opponent seat: {oc.opponent_seat}")
    if oc.use_non_chosen_suit:
        print(f"{indent}  Target: opponent's UNCHOSEN suit")
    else:
        print(f"{indent}  Target: opponent's CHOSEN suit")
    _print_suit_range("Suit", oc.suit_range, indent + "  ")


def _print_profile_metadata(profile: HandProfile, path: Path) -> None:
    """Print profile metadata header (name, tag, dealer, etc.)."""
    print(f"Name        : {profile.profile_name}")
    print(f"Description : {profile.description}")
    print(f"Tag         : {profile.tag}")
    print(f"Dealer      : {profile.dealer}")
    print(f"Author      : {profile.author}")
    print(f"Version     : {profile.version}")
    print(f"Rotate deals: {profile.rotate_deals_by_default}")

    ns_mode = profile.ns_role_mode
    ns_mode_pretty = {
        "north_drives": "North usually drives",
        "south_drives": "South usually drives",
        "random_driver": "Random between N/S",
    }.get(ns_mode, ns_mode)
    print(f"NS mode     : {ns_mode_pretty}")

    ew_mode = profile.ew_role_mode
    ew_mode_pretty = {
        "east_drives": "East usually drives",
        "west_drives": "West usually drives",
        "random_driver": "Random between E/W",
    }.get(ew_mode, ew_mode)
    print(f"EW mode     : {ew_mode_pretty}")
    print(f"File name   : {path.name}")


def _print_profile_constraints(profile: HandProfile) -> None:
    """Print per-seat constraints (subprofiles, RS, PC, OC, exclusions)."""
    print("\nSeat profiles (in dealing order):")
    for seat in profile.hand_dealing_order:
        sp = profile.seat_profiles.get(seat)
        if sp is None:
            continue

        print(f"\n--- Seat {seat} ---")
        print(f"Number of sub-profiles: {len(sp.subprofiles)}")

        multi = len(sp.subprofiles) > 1

        for idx, sub in enumerate(sp.subprofiles, start=1):
            print(f"\n  {sub_label(idx, sub)}:")
            if multi:
                print(f"    Weight: {sub.weight_percent:.1f}%")

            print("    Standard constraints:")
            _print_standard_constraints(sub.standard, indent="      ")

            if sub.random_suit_constraint is not None:
                _print_random_suit_constraint(sub.random_suit_constraint, indent="    ")

            if sub.partner_contingent_constraint is not None:
                _print_partner_contingent_constraint(
                    sub.partner_contingent_constraint,
                    indent="    ",
                )

            oc_constraint = sub.opponents_contingent_suit_constraint
            if oc_constraint is not None:
                _print_opponent_contingent_constraint(
                    oc_constraint,
                    indent="    ",
                )

        _print_subprofile_exclusions(profile, seat, indent="  ")


def _print_full_profile_details_impl(profile: HandProfile, path: Path) -> None:
    """Print full details of a profile: metadata + constraints."""
    print("\n=== Full Profile Details ===")
    _print_profile_metadata(profile, path)
    _print_profile_constraints(profile)


def _default_clockwise_order_starting_with(dealer: str) -> List[str]:
    """Clockwise from dealer — delegates to hand_profile_model."""
    from .hand_profile_model import _default_dealing_order

    d = (dealer or "").strip().upper()
    return _default_dealing_order(d if d in ("N", "E", "S", "W") else "N")


def _print_subprofile_exclusions(
    profile: HandProfile,
    seat: str,
    indent: str = "",
) -> None:
    exclusions = profile.subprofile_exclusions
    relevant = [e for e in exclusions if e.seat == seat]
    if not relevant:
        return

    print(f"{indent}Exclusions:")
    # Look up SeatProfile once for sub_label display.
    sp = profile.seat_profiles.get(seat)

    for e in relevant:
        idx = e.subprofile_index
        # Build display label with name if available (idx is 1-based).
        if sp and 1 <= idx <= len(sp.subprofiles):
            label = sub_label(idx, sp.subprofiles[idx - 1])
        else:
            label = f"Sub-profile {idx}"

        shapes = e.excluded_shapes
        if shapes:
            shapes_txt = ", ".join(str(s) for s in shapes)
            print(f"{indent}  {label}: exclude shapes: {shapes_txt}")
            continue

        clauses = e.clauses
        if clauses:
            parts = []
            for c in clauses:
                group = c.group
                length_eq = c.length_eq
                count = c.count
                parts.append(f"({group} len={length_eq} count={count})")
            print(f"{indent}  {label}: exclude if: " + " AND ".join(parts))
            continue

        print(f"{indent}  {label}: (invalid exclusion: no shapes/clauses)")


def view_and_optional_print_profile_action() -> None:
    """
    Show profile metadata + summary, then offer to print full constraints.

    This is your "View and print profile" option.
    """
    profiles = _load_profiles()
    chosen = _choose_profile(profiles)
    if chosen is None:
        return
    path, profile = chosen

    # Metadata (printed once — shared helper avoids duplication)
    print("\n--- Profile Summary ---")
    _print_profile_metadata(profile, path)

    # Offer to print full constraints (default = YES)
    print_full = prompt_yes_no(
        "\nPrint full constraints?",
        default=True,
    )
    if print_full:
        _print_profile_constraints(profile)

    # Optional: export full profile details to TXT under out/profile_constraints/
    export_txt = prompt_yes_no(
        "\nWrite full profile details to TXT under out/profile_constraints/?",
        default=False,
    )
    if export_txt:
        name = (profile.profile_name or "profile").strip()
        tag = (profile.tag or "Tag").strip()

        safe_name = "".join(c if (c.isalnum() or c in ("-", "_")) else "_" for c in name)
        safe_tag = "".join(c if (c.isalnum() or c in ("-", "_")) else "_" for c in tag)

        # Write constraints to out/profile_constraints (created if needed)
        out_root = Path(__file__).resolve().parent.parent / "out" / "profile_constraints"
        out_root.mkdir(parents=True, exist_ok=True)

        out_path = out_root / f"{safe_name}_{safe_tag}_constraints.txt"

        buf = io.StringIO()
        with redirect_stdout(buf):
            _print_full_profile_details_impl(profile, path)

        out_path.write_text(buf.getvalue(), encoding="utf-8")
        print(f"\nWrote full profile details to: {out_path}")


def edit_profile_action() -> None:
    """
    Edit an existing profile.

    User can choose:
        - Edit metadata only
        - Edit constraints only (keeping current constraints as defaults)

    After each edit, returns to the edit menu for the same profile
    so the user can make further changes without re-selecting.
    """
    profiles = _load_profiles()
    chosen = _choose_profile(profiles)
    if chosen is None:
        return

    path, profile = chosen

    while True:
        print(f"\nEditing profile: {profile.profile_name}")

        print("\nEdit mode:")
        print("  0) Done (back to Profile Manager)")
        print("  1) Edit metadata only")
        print("  2) Edit constraints only")
        print("  3) Edit sub-profile names")
        print("  4) Help")
        mode = _input_int(
            "Choose [0-4] [0]: ",
            default=0,
            minimum=0,
            maximum=4,
            show_range_suffix=False,
        )

        if mode == 0:
            return

        if mode == 4:
            print(get_menu_help("edit_profile_mode"))
            continue

        print()

        if mode == 1:
            # ------------------------
            # Metadata-only edit
            # ------------------------
            new_name = _input_with_default("Profile name", profile.profile_name)
            new_desc = _input_with_default("Description", profile.description)
            new_tag = prompt_choice(
                "Tag (Opener / Overcaller)",
                ["OPENER", "OVERCALLER"],
                profile.tag.upper(),
            ).capitalize()
            new_dealer = prompt_choice("Dealer seat", ["N", "E", "S", "W"], profile.dealer).upper()

            # Dealing order is auto-computed at runtime by v2 builder.
            # Store clockwise from dealer as default; not user-editable.
            dealer = (new_dealer or profile.dealer or "N").strip().upper()
            new_order = _default_clockwise_order_starting_with(dealer)

            new_author = _input_with_default("Author", profile.author)
            new_version = _input_with_default("Version", profile.version)

            rotate_default = _yes_no(
                "Rotate deals by default?",
                profile.rotate_deals_by_default,
            )

            # NS role mode (5 options)
            existing_ns_mode = profile.ns_role_mode or "no_driver_no_index"
            ns_mode_options = [
                ("north_drives", "North almost always drives"),
                ("south_drives", "South almost always drives"),
                (
                    "random_driver",
                    "Random driver (per board) – N or S is randomly assigned to drive the hand",
                ),
                (
                    "no_driver",
                    "Index matching – no driver",
                ),
                ("no_driver_no_index", "No driver / no index matching"),
            ]

            ns_default_label = next(
                (label for m, label in ns_mode_options if m == existing_ns_mode),
                "No driver / no index matching",
            )

            default_idx = next(
                (i for i, (_, label) in enumerate(ns_mode_options, start=1) if label == ns_default_label),
                len(ns_mode_options),
            )

            # Number of real mode options (help is appended as last item)
            n_modes = len(ns_mode_options)
            help_idx = n_modes + 1

            while True:
                print("NS role mode (who probably drives the auction for NS?)")
                for i, (_, label) in enumerate(ns_mode_options, start=1):
                    print(f"  {i}) {label}")
                print(f"  {help_idx}) Help")

                choice = _input_int(
                    f"Choose [1-{help_idx}]",
                    default=default_idx,
                    minimum=1,
                    maximum=help_idx,
                    show_range_suffix=False,
                )

                if choice == help_idx:
                    print(get_menu_help("ns_role_mode"))
                    continue

                break

            new_ns_role_mode = ns_mode_options[choice - 1][0]

            # EW role mode (5 options, parallel to NS)
            existing_ew_mode = profile.ew_role_mode or "no_driver_no_index"
            ew_mode_options = [
                ("east_drives", "East almost always drives"),
                ("west_drives", "West almost always drives"),
                (
                    "random_driver",
                    "Random driver (per board) – E or W is randomly assigned to drive the hand",
                ),
                (
                    "no_driver",
                    "Index matching – no driver",
                ),
                ("no_driver_no_index", "No driver / no index matching"),
            ]

            ew_default_label = next(
                (label for m, label in ew_mode_options if m == existing_ew_mode),
                "No driver / no index matching",
            )

            ew_default_idx = next(
                (i for i, (_, label) in enumerate(ew_mode_options, start=1) if label == ew_default_label),
                len(ew_mode_options),
            )

            ew_n_modes = len(ew_mode_options)
            ew_help_idx = ew_n_modes + 1

            while True:
                print("EW role mode (who probably drives the auction for EW?)")
                for i, (_, label) in enumerate(ew_mode_options, start=1):
                    print(f"  {i}) {label}")
                print(f"  {ew_help_idx}) Help")

                ew_choice = _input_int(
                    f"Choose [1-{ew_help_idx}]",
                    default=ew_default_idx,
                    minimum=1,
                    maximum=ew_help_idx,
                    show_range_suffix=False,
                )

                if ew_choice == ew_help_idx:
                    print(get_menu_help("ew_role_mode"))
                    continue

                break

            new_ew_role_mode = ew_mode_options[ew_choice - 1][0]

            updated = HandProfile(
                profile_name=new_name,
                description=new_desc,
                dealer=new_dealer,
                hand_dealing_order=new_order,
                tag=new_tag,
                seat_profiles=profile.seat_profiles,
                author=new_author,
                version=new_version,
                rotate_deals_by_default=rotate_default,
                ns_role_mode=new_ns_role_mode,
                ew_role_mode=new_ew_role_mode,
                subprofile_exclusions=list(profile.subprofile_exclusions),
                is_invariants_safety_profile=profile.is_invariants_safety_profile,
                sort_order=profile.sort_order,
            )

            # If name or version changed, save to a new file (keep old file intact)
            new_path = _profile_path_for(updated)
            _save_profile_to_path(updated, new_path)
            profile_store.delete_draft_for_canonical(new_path)
            if new_path != path:
                print(f"\nSaved to new file: {new_path.name}")
                print(f"Previous file kept: {path.name}")
            else:
                print(f"\nUpdated profile saved to {new_path.name}")
            # Update references so next loop iteration uses the saved version
            path = new_path
            profile = updated

        elif mode == 2:
            # ------------------------
            # Constraints-only edit
            # ------------------------
            try:
                updated = edit_constraints_interactive_flow(profile, profile_path=path)
            except ProfileError as exc:
                print(f"ERROR while editing constraints: {exc}")
                continue

            print()  # Visual separator before save prompt
            if prompt_yes_no("Save updated constraints to this profile?", True):
                _save_profile_to_path(updated, path)
                profile_store.delete_draft_for_canonical(path)
                print(f"\nUpdated profile saved to {path}")
                # Update profile so next loop iteration uses the saved version
                profile = updated

        elif mode == 3:
            # ------------------------
            # Edit sub-profile names
            # ------------------------
            updated_seats = dict(profile.seat_profiles)
            changed = False

            for seat in ("N", "E", "S", "W"):
                sp = updated_seats.get(seat)
                if sp is None or not sp.subprofiles:
                    continue

                print(f"\n--- Seat {seat} ({len(sp.subprofiles)} sub-profile(s)) ---")
                new_subs = list(sp.subprofiles)
                for idx, sub in enumerate(sp.subprofiles, start=1):
                    # Show subprofile constraints so user knows what they're naming.
                    print(f"\n  {sub_label(idx, sub)}:")
                    print("    Standard constraints:")
                    _print_standard_constraints(sub.standard, indent="      ")
                    if sub.random_suit_constraint is not None:
                        _print_random_suit_constraint(sub.random_suit_constraint, indent="    ")
                    if sub.partner_contingent_constraint is not None:
                        _print_partner_contingent_constraint(sub.partner_contingent_constraint, indent="    ")
                    if sub.opponents_contingent_suit_constraint is not None:
                        _print_opponent_contingent_constraint(sub.opponents_contingent_suit_constraint, indent="    ")

                    current = sub.name or ""
                    hint = f" [{current}]" if current else ""
                    raw = _input_with_default(
                        f"  Name for {sub_label(idx, sub)}{hint}",
                        current,
                    )
                    new_name_val = raw.strip() or None
                    if new_name_val != sub.name:
                        new_subs[idx - 1] = replace(sub, name=new_name_val)
                        changed = True

                updated_seats[seat] = SeatProfile(seat=seat, subprofiles=new_subs)

            if changed:
                updated = HandProfile(
                    profile_name=profile.profile_name,
                    description=profile.description,
                    dealer=profile.dealer,
                    hand_dealing_order=profile.hand_dealing_order,
                    tag=profile.tag,
                    seat_profiles=updated_seats,
                    author=profile.author,
                    version=profile.version,
                    rotate_deals_by_default=profile.rotate_deals_by_default,
                    ns_role_mode=profile.ns_role_mode,
                    ew_role_mode=profile.ew_role_mode,
                    subprofile_exclusions=list(profile.subprofile_exclusions),
                    is_invariants_safety_profile=profile.is_invariants_safety_profile,
                    sort_order=profile.sort_order,
                )
                _save_profile_to_path(updated, path)
                profile_store.delete_draft_for_canonical(path)
                print(f"\nSub-profile names updated and saved to {path.name}")
                profile = updated
            else:
                print("\nNo changes made.")


def delete_profile_action() -> None:
    profiles = _load_profiles()
    chosen = _choose_profile(profiles)
    if chosen is None:
        return
    path, profile = chosen
    if prompt_yes_no(f"Really delete profile '{profile.profile_name}'?", False):
        try:
            path.unlink()
            print(f"Deleted {path}")
        except OSError as exc:
            print(f"Failed to delete {path}: {exc}")


def save_as_new_version_action() -> None:
    """
    Save a chosen profile as a new version (e.g. v0.2 -> v0.3).
    """
    profiles = _load_profiles()
    chosen = _choose_profile(profiles)
    if chosen is None:
        return
    _, profile = chosen

    current_version = profile.version or "0.1"
    print(f"Current version: {current_version}")
    new_version = _input_with_default("New version", current_version)

    new_profile = HandProfile(
        profile_name=profile.profile_name,
        description=profile.description,
        dealer=profile.dealer,
        hand_dealing_order=profile.hand_dealing_order,
        tag=profile.tag,
        seat_profiles=profile.seat_profiles,
        author=profile.author,
        version=new_version,
        rotate_deals_by_default=profile.rotate_deals_by_default,
        ns_role_mode=profile.ns_role_mode,
        ew_role_mode=profile.ew_role_mode,
        subprofile_exclusions=list(profile.subprofile_exclusions),
        is_invariants_safety_profile=profile.is_invariants_safety_profile,
        sort_order=profile.sort_order,
    )

    validate_profile(new_profile)
    path = _profile_path_for(new_profile)
    _save_profile_to_path(new_profile, path)
    profile_store.delete_draft_for_canonical(path)


# ---------------------------------------------------------------------------
# Top-level menu
# ---------------------------------------------------------------------------


def run_profile_manager() -> None:
    """
    Top-level Profile Manager menu.

    0) Exit
    1) List profiles
    2) View / print profile (full details)
    3) Edit profile
    4) Create new profile
    5) Delete profile
    6) Save profile as new version
    7) Help
    """
    while True:
        print("\n=== Bridge Hand Generator – Profile Manager ===")
        print("0) Exit")
        print("1) List profiles")
        print("2) View / print profile (full details)")
        print("3) Edit profile")
        print("4) Create new profile")
        print("5) Delete profile")
        print("6) Save profile as new version")
        print("7) Help")

        choice = _input_int(
            "Choose [0-7] [0]: ",
            default=0,
            minimum=0,
            maximum=7,
            show_range_suffix=False,
        )

        if choice == 0:
            # Back to main menu
            break
        elif choice == 1:
            list_profiles_action()
        elif choice == 2:
            view_and_optional_print_profile_action()
        elif choice == 3:
            try:
                edit_profile_action()
            except (KeyboardInterrupt, SystemExit):
                raise
            except Exception as exc:
                # Top-level safety net: the wizard calls many subsystems,
                # so any exception type is possible.  Log and continue.
                print("\nWARNING: Wizard error — returning to Profile Manager.")
                print(f"   {type(exc).__name__}: {exc}\n")
        elif choice == 4:
            try:
                create_profile_action()
            except (KeyboardInterrupt, SystemExit):
                raise
            except Exception as exc:
                # Top-level safety net (same rationale as edit above).
                print("\nWARNING: Wizard error — returning to Profile Manager.")
                print(f"   {type(exc).__name__}: {exc}\n")
        elif choice == 5:
            delete_profile_action()
        elif choice == 6:
            save_as_new_version_action()
        elif choice == 7:
            # Profile Manager specific help
            print(get_menu_help("profile_manager_menu"))


def run_draft_tools() -> None:
    """Wrapper called by orchestrator.py to run draft tools."""
    draft_tools_action()


def main() -> None:
    """Entry point so orchestrator can call profile_cli.main()."""
    run_profile_manager()


if __name__ == "__main__":
    main()
