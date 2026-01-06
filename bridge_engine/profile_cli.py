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

from .menu_help import get_menu_help
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

from . import profile_store
from . import profile_wizard

from .wizard_flow import edit_constraints_interactive as edit_constraints_interactive_flow

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

    print("\nView or Edit Profiles on disk:")
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


def _create_profile_from_base_template() -> None:
    """
    Create a new profile using a standard base template.

    For now we hard-code Base_v1.0, but this could later be a menu with
    Base_va / Base_vb, etc.
    """
    base_entry = profile_store.find_profile_by_name("Base_v1.0")
    if base_entry is None:
        print("ERROR: Base_v1.0 template not found; falling back to full wizard.")
        profile = profile_wizard.create_profile_interactive()
    else:
        base_profile = base_entry.profile
        profile = profile_wizard.create_profile_from_existing_constraints(base_profile)

    # Whatever save logic you already use after create_profile_interactive()
    profile_store.save_profile(profile)
    print(f"Saved new profile: {profile.profile_name}")


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


def draft_tools_action() -> None:
    profiles_dir = _profiles_dir()  # or however profile_cli resolves profiles/
    drafts = profile_store.list_drafts(profiles_dir)

    if not drafts:
        print("\nNo draft *_TEST.json files found.")
        return

    print("\nDraft *_TEST.json files:")
    for i, p in enumerate(drafts, start=1):
        print(f"  {i}) {p.name}")

    print("\nActions:")
    print("  1) Delete one draft")
    print("  2) Delete ALL drafts")
    print("  3) Cancel")

    action = _input_int("Choose [1-3]", default=3, minimum=1, maximum=3, show_range_suffix=False)
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
    print("Rotate set to Yes and NS role mode set to Any")
    print()
    print("Metadata can be chnaged in 'Edit Profile'")

    if prompt_yes_no("Save this new profile?", True):
        path = _profile_path_for(profile)
        _save_profile_to_path(profile, path)
        profile_store.delete_draft_for_canonical(path)


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
    
    ns_mode = getattr(profile, "ns_role_mode", "north_drives")
    ns_mode_pretty = {
        "north_drives": "North usually drives",
        "south_drives": "South usually drives",
        "random_driver": "Random between N/S",
    }.get(ns_mode, ns_mode)
    print(f"NS mode: {ns_mode_pretty}")
    
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


def _parse_hand_dealing_order(s: str) -> list[str] | None:
    """
    Parse a hand dealing order from user input.
    Accepts formats like: "N E S W", "nesw", "w,n,e,s", "W N E S".
    Returns a list like ["N","E","S","W"] or None if invalid.
    """
    if s is None:
        return None
    raw = s.strip().upper()
    if not raw:
        return None

    # Split on whitespace/commas if present; otherwise treat as a 4-letter string.
    if any(ch in raw for ch in (" ", ",", "\t")):
        parts = [p for p in raw.replace(",", " ").split() if p]
    else:
        parts = list(raw)

    if len(parts) != 4:
        return None
    if set(parts) != {"N", "E", "S", "W"}:
        return None
    return parts


def _default_clockwise_order_starting_with(dealer: str) -> list[str]:
    base = ["N", "E", "S", "W"]
    dealer = (dealer or "").strip().upper()
    if dealer not in base:
        return base
    i = base.index(dealer)
    return base[i:] + base[:i]


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
    print(f"\nEditing profile: {profile.profile_name}")

    print("\nEdit mode:")
    print("  1) Edit metadata only")
    print("  2) Edit constraints only")
    mode = _input_int(
        "Choose [1-2]",
        default=1,
        minimum=1,
        maximum=2,
        show_range_suffix=False,
    )
    
    print()

    if mode == 1:
        # ------------------------
        # Metadata-only edit
        # ------------------------
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
        new_dealer = prompt_choice("Dealer seat", ["N", "E", "S", "W"], profile.dealer).upper()

        # Dealing order (robust parsing + invariant enforcement)
        print(f"Current hand dealing order: {profile.hand_dealing_order}")
        order_in = input(
            "Hand dealing order (4 seats, e.g. 'N E S W' or 'NESW') "
            f"[{' '.join(profile.hand_dealing_order)}]: "
        ).strip()

        new_order = None
        if order_in:
            parsed = _parse_hand_dealing_order(order_in)
            if parsed is None:
                print(
                    "Invalid dealing order input; will keep current "
                    "(but will be adjusted if dealer changed)."
                )
            else:
                new_order = parsed

        if new_order is None:
            new_order = list(profile.hand_dealing_order)

        dealer = (new_dealer or profile.dealer or "N").strip().upper()

        if new_order[0] != dealer:
            if dealer in new_order:
                i = new_order.index(dealer)
                new_order = new_order[i:] + new_order[:i]
                print(f"Adjusted dealing order to start with dealer {dealer}: {new_order}")
            else:
                new_order = _default_clockwise_order_starting_with(dealer)
                print(f"Replaced dealing order with default starting with dealer {dealer}: {new_order}")

        new_author = _input_with_default("Author", getattr(profile, "author", ""))
        new_version = _input_with_default("Version", getattr(profile, "version", ""))

        rotate_default = _yes_no(
            "Rotate deals by default?",
            getattr(profile, "rotate_deals_by_default", True),
        )

        # NS role mode (5 options)
        existing_ns_mode = getattr(profile, "ns_role_mode", None) or "no_driver_no_index"
        ns_mode_options = [
            ("north_drives", "North almost always drives"),
            ("south_drives", "South almost always drives"),
            (
                "random_driver",
                "Random driver (per board) – N or S is randomly assigned to drive the hand",
            ),
            (
                "no_driver",
                "No Driver – neither N or S explicitly drives, but SubProfile [index] matching applies",
            ),
            ("no_driver_no_index", "No driver / no index matching"),
        ]

        ns_default_label = next(
            (label for m, label in ns_mode_options if m == existing_ns_mode),
            "No driver / no index matching",
        )

        print("NS role mode (who probably drives the auction for NS?)")
        for i, (_, label) in enumerate(ns_mode_options, start=1):
            print(f"  {i}) {label}")

        default_idx = next(
            (i for i, (_, label) in enumerate(ns_mode_options, start=1) if label == ns_default_label),
            len(ns_mode_options),
        )

        choice = _input_int(
            f"Choose [1-{len(ns_mode_options)}]",
            default=default_idx,
            minimum=1,
            maximum=len(ns_mode_options),
            show_range_suffix=False,
        )

        new_ns_role_mode = ns_mode_options[choice - 1][0]

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
        )

        _save_profile_to_path(updated, path)
        profile_store.delete_draft_for_canonical(path)
        print(f"\nUpdated profile saved to {path}")
        return

    else:        # ------------------------
        # Constraints-only edit
        # ------------------------
        try:
            updated = edit_constraints_interactive_flow(profile, profile_path=path)
        except ProfileError as exc:
            print(f"ERROR while editing constraints: {exc}")
            return

        if prompt_yes_no("Save updated constraints to this profile?", True):
            _save_profile_to_path(updated, path)
            print(f"\nUpdated profile saved to {path}")
        return


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
            except Exception as e:
                print("\n⚠️ Wizard error — returning to Profile Manager.")
                print(f"   {type(e).__name__}: {e}\n")
        elif choice == 4:
            try:
                create_profile_action()
            except (KeyboardInterrupt, SystemExit):
                raise
            except Exception as e:
                print("\n⚠️ Wizard error — returning to Profile Manager.")
                print(f"   {type(e).__name__}: {e}\n")
        elif choice == 5:
            delete_profile_action()
        elif choice == 6:
            save_as_new_version_action()
        elif choice == 7:
            # Profile Manager specific help
            print(get_menu_help("profile_manager_menu"))                       

def draft_tools_action() -> None:
    print("\nDraft tools are not implemented yet.")


def main() -> None:
    """Entry point so orchestrator can call profile_cli.main()."""
    run_profile_manager()


if __name__ == "__main__":
    main()
