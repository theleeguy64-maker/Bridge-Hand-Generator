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
import sys
import io
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from .cli_io import _yes_no as _yes_no  # keep name for tests to monkeypatch

from .hand_profile import (
    SuitRange,
    RandomSuitConstraintData,
    PartnerContingentData,
    OpponentContingentSuitData,
    StandardSuitConstraints,
    SubProfile,
    SeatProfile,
    HandProfile,
    ProfileError,
    validate_profile,
)


from .profile_wizard import (
    create_profile_interactive,
    edit_constraints_interactive,
)


PROFILE_DIR_NAME = "profiles"
SUITS: List[str] = ["S", "H", "D", "C"]


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


def prompt_choice(
    prompt: str, choices: List[str], default: Optional[str] = None
) -> str:
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
    version = getattr(profile, "version", "")
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
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            profile = HandProfile.from_dict(data)
            results.append((path, profile))
        except Exception as exc:
            print(
                f"WARNING: Failed to load profile from {path}: {exc}",
                file=sys.stderr,
            )
    return results


def _save_profile_to_path(profile: HandProfile, path: Path) -> None:
    """Save profile as JSON to the given path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = profile.to_dict()
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=False)
    print(f"Profile saved to {path}")


# ---------------------------------------------------------------------------
# Menu actions
# ---------------------------------------------------------------------------


def _choose_profile(
    profiles: List[Tuple[Path, HandProfile]]
) -> Optional[Tuple[Path, HandProfile]]:
    """Let user pick a profile by number. Returns (path, profile) or None."""
    if not profiles:
        print("No profiles found.")
        return None

    print("\nProfiles on disk:")
    for idx, (path, profile) in enumerate(profiles, start=1):
        print(
            f"  {idx}) {profile.profile_name} "
            f"(v{getattr(profile, 'version', '')}, "
            f"tag={profile.tag}, dealer={profile.dealer})"
        )

    choice = _input_int(
        "Choose profile number (0 to cancel)",
        default=0,
        minimum=0,
        maximum=len(profiles),
        show_range_suffix=False,
    )
    if choice == 0:
        return None
    if 1 <= choice <= len(profiles):
        return profiles[choice - 1]
    print("Invalid choice.")
    return None


def list_profiles_action() -> None:
    profiles = _load_profiles()
    if not profiles:
        print("\nNo profiles created yet.")
        return

    print("\nProfiles on disk:")
    for idx, (path, profile) in enumerate(profiles, start=1):
        print(
            f"  {idx}) {profile.profile_name} "
            f"(v{getattr(profile, 'version', '')}, "
            f"tag={profile.tag}, dealer={profile.dealer})"
        )


def create_profile_action() -> None:
    profile = create_profile_interactive()
    if prompt_yes_no("Save this new profile?", True):
        path = _profile_path_for(profile)
        _save_profile_to_path(profile, path)


def _print_suit_range(label: str, r: SuitRange, indent: str = "") -> None:
    print(
        f"{indent}{label}: cards {r.min_cards}–{r.max_cards}, "
        f"HCP {r.min_hcp}–{r.max_hcp}"
    )

def _fmt_suits(suits) -> str:
    """
    Format suits as a stable ordered list: [S,H,D,C]
    Accepts list/tuple/set or a compact string like "SH".
    """
    if suits is None:
        return "[]"
    if isinstance(suits, str):
        suits_list = list(suits)
    else:
        suits_list = list(suits)

    order = ["S", "H", "D", "C"]
    suits_sorted = [s for s in order if s in set(suits_list)]
    # Fallback: if something unexpected came in, keep what we got
    if not suits_sorted:
        suits_sorted = suits_list

    return "[" + ",".join(suits_sorted) + "]"

def _print_standard_constraints(std: StandardSuitConstraints, indent: str = "") -> None:
    print(
        f"{indent}Total HCP: {std.total_min_hcp}–{std.total_max_hcp} "
        "(for entire hand)"
    )
    _print_suit_range("Spades", std.spades, indent + "  ")
    _print_suit_range("Hearts", std.hearts, indent + "  ")
    _print_suit_range("Diamonds", std.diamonds, indent + "  ")
    _print_suit_range("Clubs", std.clubs, indent + "  ")


def _print_random_suit_constraint(
    rs: RandomSuitConstraintData, indent: str = ""
) -> None:
    suits_txt = _fmt_suits(rs.allowed_suits)
    req = rs.required_suits_count

    print(f"{indent}Random Suit: {req} of {suits_txt} must meet:")
    for idx, r in enumerate(rs.suit_ranges, start=1):
        print(
            f"{indent}  #{idx}: cards {r.min_cards}–{r.max_cards}, "
            f"HCP {r.min_hcp}–{r.max_hcp}"
        )

    if rs.pair_overrides:
        print(f"{indent}  Pair overrides:")
        for o in rs.pair_overrides:
            suits = getattr(o, "suits", None)
            first_range = getattr(o, "first_range", None)
            second_range = getattr(o, "second_range", None)
            if suits is None:
                suits = o.get("suits")
                first_range = o.get("first_range")
                second_range = o.get("second_range")

            suits2 = _fmt_suits(suits)

            parts: list[str] = []
            if first_range is not None:
                parts.append(
                    f"first cards {first_range.min_cards}–{first_range.max_cards}, "
                    f"HCP {first_range.min_hcp}–{first_range.max_hcp}"
                )
            if second_range is not None:
                parts.append(
                    f"second cards {second_range.min_cards}–{second_range.max_cards}, "
                    f"HCP {second_range.min_hcp}–{second_range.max_hcp}"
                )

            if parts:
                print(f"{indent}    {suits2}: " + "; ".join(parts))
            else:
                print(f"{indent}    {suits2}")


def _print_partner_contingent_constraint(
    pc: PartnerContingentData, indent: str = ""
) -> None:
    print(f"{indent}Partner Contingent constraint:")
    print(f"{indent}  Partner seat: {pc.partner_seat}")
    _print_suit_range("Suit", pc.suit_range, indent + "  ")

def _print_opponent_contingent_constraint(
    oc: OpponentContingentSuitData, indent: str = ""
) -> None:
    print(f"{indent}Opponent Contingent-Suit constraint:")
    print(f"{indent}  Opponent seat: {oc.opponent_seat}")
    _print_suit_range("Suit", oc.suit_range, indent + "  ")

def _render_full_profile_details_text(profile: HandProfile, path: Path) -> str:
    """
    Render the full profile details (same format as _print_full_profile_details)
    into a single string.
    """
    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        # Reuse the existing printer's logic *temporarily* by capturing stdout.
        # BUT: we must avoid recursion, so this helper must be called by the printer,
        # not call the printer.
        #
        # Therefore: move the original print logic into a private inner function.
        pass  # replaced below

def _print_full_profile_details_impl(profile: HandProfile, path: Path) -> None:
    """Print full details of a profile, including constraints."""
    print("\n=== Full Profile Details ===")
    print(f"Name        : {profile.profile_name}")
    print(f"Description : {profile.description}")
    print(f"Tag         : {profile.tag}")
    print(f"Dealer      : {profile.dealer}")
    print(f"Author      : {getattr(profile, 'author', '')}")
    print(f"Version     : {getattr(profile, 'version', '')}")
    print(f"File        : {path}")
    print(f"Dealing ord.: {profile.hand_dealing_order}")
    print(f"Rotate deals: {getattr(profile, 'rotate_deals_by_default', True)}")
    
    print("\nSeat profiles (in dealing order):")
    for seat in profile.hand_dealing_order:
        sp = profile.seat_profiles.get(seat)
        if sp is None:
            continue

        print(f"\n--- Seat {seat} ---")
        print(f"Number of sub-profiles: {len(sp.subprofiles)}")

        multi = len(sp.subprofiles) > 1

        for idx, sub in enumerate(sp.subprofiles, start=1):
            print(f"\n  Sub-profile {idx}:")
            if multi:
                weight = getattr(sub, "weight_percent", None)
                if weight is not None:
                    print(f"    Weight: {weight:.1f}%")

            print("    Standard constraints:")
            _print_standard_constraints(sub.standard, indent="      ")

            if sub.random_suit_constraint is not None:
                _print_random_suit_constraint(sub.random_suit_constraint, indent="    ")

            if sub.partner_contingent_constraint is not None:
                _print_partner_contingent_constraint(
                    sub.partner_contingent_constraint,
                    indent="    ",
                )

            if getattr(sub, "opponents_contingent_suit_constraint", None) is not None:
                _print_opponent_contingent_constraint(
                    sub.opponents_contingent_suit_constraint,
                    indent="    ",
                )
                
        _print_subprofile_exclusions(profile, seat, indent="  ")


def _print_full_profile_details(profile: HandProfile, path: Path) -> None:
    """Print full details of a profile, including constraints."""
    _print_full_profile_details_impl(profile, path)

def _print_subprofile_exclusions(
    profile: HandProfile,
    seat: str,
    indent: str = "",
) -> None:
    exclusions = getattr(profile, "subprofile_exclusions", [])
    relevant = [
        e for e in exclusions
        if getattr(e, "seat", None) == seat
    ]
    if not relevant:
        return

    print(f"{indent}Exclusions:")
    for e in relevant:
        idx = getattr(e, "subprofile_index", None)

        shapes = getattr(e, "excluded_shapes", None)
        if shapes:
            shapes_txt = ", ".join(str(s) for s in shapes)
            print(f"{indent}  Sub-profile {idx}: exclude shapes: {shapes_txt}")
            continue

        clauses = getattr(e, "clauses", None)
        if clauses:
            parts = []
            for c in clauses:
                group = getattr(c, "group", "")
                length_eq = getattr(c, "length_eq", None)
                count = getattr(c, "count", None)
                parts.append(f"({group} len={length_eq} count={count})")
            print(f"{indent}  Sub-profile {idx}: exclude if: " + " AND ".join(parts))
            continue

        print(f"{indent}  Sub-profile {idx}: (invalid exclusion: no shapes/clauses)")

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

    # Summary / metadata
    print("\n--- Profile Summary ---")
    print(f"Name        : {profile.profile_name}")
    print(f"Description : {profile.description}")
    print(f"Tag         : {profile.tag}")
    print(f"Dealer      : {profile.dealer}")
    print(f"Author      : {getattr(profile, 'author', '')}")
    print(f"Version     : {getattr(profile, 'version', '')}")
    print(f"File        : {path}")
    print(f"Dealing ord.: {profile.hand_dealing_order}")
    print("Seat profiles:")
    for seat in profile.hand_dealing_order:
        sp = profile.seat_profiles.get(seat)
        if sp is None:
            continue
        print(f"  Seat {seat}: {len(sp.subprofiles)} sub-profile(s)")
        exclusions = [
            e for e in getattr(profile, "subprofile_exclusions", [])
            if getattr(e, "seat", None) == seat
        ]
        if exclusions:
            items = []
            for e in exclusions:
                idx = getattr(e, "subprofile_index", None)
                if getattr(e, "excluded_shapes", None):
                    items.append(f"{idx}:shapes")
                elif getattr(e, "clauses", None):
                    items.append(f"{idx}:rule")
                else:
                    items.append(f"{idx}:?")
            print(f"    Exclusions: " + ", ".join(items))
            
    # Offer to print full constraints (default = YES)
    print_full = prompt_yes_no(
        "\nPrint full profile details including constraints?",
        default=True,
    )
    if print_full:
        _print_full_profile_details(profile, path)

    # Optional: export full profile details to TXT under out/profile_constraints/
    export_txt = prompt_yes_no(
        "\nWrite full profile details to TXT under out/profile_constraints/?",
        default=False,
    )
    if export_txt:
        name = (getattr(profile, "profile_name", "profile") or "profile").strip()
        tag = (getattr(profile, "tag", "Tag") or "Tag").strip()

        safe_name = "".join(
            c if (c.isalnum() or c in ("-", "_")) else "_" for c in name
        )
        safe_tag = "".join(
            c if (c.isalnum() or c in ("-", "_")) else "_" for c in tag
        )

        # Write constraints to out/profile_constraints (created if needed)
        out_root = (
            Path(__file__).resolve().parent.parent / "out" / "profile_constraints"
        )
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
    """
    profiles = _load_profiles()
    chosen = _choose_profile(profiles)
    if chosen is None:
        return

    path, profile = chosen
    print(f"\nEditing profile: {profile.profile_name} (file: {path})")

    print("\nEdit mode:")
    print("  1) Edit metadata only")
    print("  2) Edit constraints only")
    mode = _input_int("Choose [1-2]", default=1, minimum=1, maximum=2)

    if mode == 1:
        # Metadata-only edit
        new_name = _input_with_default("Profile name", profile.profile_name)
        new_desc = _input_with_default("Description", profile.description)
        new_tag = (
            prompt_choice(
                "Tag (Opener / Overcaller)",
                ["OPENER", "OVERCALLER"],
                profile.tag.upper(),
            )
            .capitalize()
        )
        new_dealer = prompt_choice(
            "Dealer seat", ["N", "E", "S", "W"], profile.dealer
        )

        print(f"Current hand dealing order: {profile.hand_dealing_order}")
        hd_default = " ".join(profile.hand_dealing_order)
        raw_order = _input_with_default(
            "Hand dealing order (4 seats, e.g. 'N E S W')", hd_default
        )
        parts = raw_order.split()
        if len(parts) != 4 or set(parts) != {"N", "E", "S", "W"}:
            print("Invalid dealing order; keeping existing order.")
            new_hand_dealing_order = profile.hand_dealing_order
        else:
            new_hand_dealing_order = parts

        new_author = _input_with_default("Author", getattr(profile, "author", ""))
        new_version = _input_with_default(
            "Version", getattr(profile, "version", "")
        )

        # Rotate flag
        rotate_default = _yes_no(
            "Rotate deals by default?",
            getattr(profile, "rotate_deals_by_default", True),
        )

        # NS role mode (who usually drives the auction for NS?)
        existing_ns_mode = getattr(profile, "ns_role_mode", "north_drives")
        ns_default_label = (
            "North usually drives"
            if existing_ns_mode == "north_drives"
            else "South usually drives"
        )
        ns_label = prompt_choice(
            "NS role mode (who usually drives the auction for NS?)",
            ["North usually drives", "South usually drives"],
            ns_default_label,
        )
        new_ns_role_mode = (
            "north_drives" if ns_label.startswith("North") else "south_drives"
        )

        updated = HandProfile(
            profile_name=new_name,
            description=new_desc,
            dealer=new_dealer,
            hand_dealing_order=new_hand_dealing_order,
            tag=new_tag,
            seat_profiles=profile.seat_profiles,
            author=new_author,
            version=new_version,
            rotate_deals_by_default=rotate_default,
            ns_role_mode=new_ns_role_mode,
        )

        _save_profile(path, updated)
        print(f"\nUpdated profile saved to {path}")
    else:
        # Constraints-only edit
        try:
            updated = edit_constraints_interactive(profile)
        except ProfileError as exc:
            print(f"ERROR while editing constraints: {exc}")
            return

        if prompt_yes_no("Save updated constraints to this profile?", True):
            _save_profile(path, updated)
            print(f"\nUpdated profile saved to {path}")

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

    current_version = getattr(profile, "version", "") or "0.1"
    print(f"Current version: {current_version}")
    new_version = _input_with_default("New version", current_version)

    new_profile = HandProfile(
        profile_name=profile.profile_name,
        description=profile.description,
        dealer=profile.dealer,
        hand_dealing_order=profile.hand_dealing_order,
        tag=profile.tag,
        seat_profiles=profile.seat_profiles,
        author=getattr(profile, "author", ""),
        version=new_version,
    )

    validate_profile(new_profile)
    path = _profile_path_for(new_profile)
    _save_profile_to_path(new_profile, path)


# ---------------------------------------------------------------------------
# Top-level menu
# ---------------------------------------------------------------------------


def run_profile_manager() -> None:
    while True:
        print("\n=== Bridge Hand Generator – Profile Manager ===")
        print("1) List profiles")
        print("2) Create new profile")
        print("3) View / print profile (full details)")
        print("4) Edit profile")
        print("5) Delete profile")
        print("6) Save profile as new version")
        print("7) Exit")

        choice = _input_int("Choose [1-7] (default 7)", default=7, minimum=1, maximum=7)

        if choice == 1:
            list_profiles_action()
        elif choice == 2:
            try:
                create_profile_action()
            except (KeyboardInterrupt, SystemExit):
                raise
            except Exception as e:
                print("\n⚠️ Wizard error — returning to main menu.")
                print(f"   {type(e).__name__}: {e}\n")
        elif choice == 3:
            view_and_optional_print_profile_action()
        elif choice == 4:
            try:
                edit_profile_action()
            except (KeyboardInterrupt, SystemExit):
                raise
            except Exception as e:
                print("\n⚠️ Wizard error — returning to main menu.")
                print(f"   {type(e).__name__}: {e}\n")
        elif choice == 5:
            delete_profile_action()
        elif choice == 6:
            save_as_new_version_action()
        else:
            print("Exiting Profile Manager.")
            break


def main() -> None:
    """Entry point so orchestrator can call profile_cli.main()."""
    run_profile_manager()


if __name__ == "__main__":
    main()
