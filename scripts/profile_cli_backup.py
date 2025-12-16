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
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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

PROFILE_DIR_NAME = "profiles"
SUITS: List[str] = ["S", "H", "D", "C"]


# ---------------------------------------------------------------------------
# Basic input helpers
# ---------------------------------------------------------------------------


def _input_with_default(prompt: str, default: str) -> str:
    """Prompt with a default string."""
    full = f"{prompt} (default {default}): "
    resp = input(full).strip()
    return resp or default


def _input_choice(
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
        resp = input(full).strip().upper()
        if not resp and default is not None:
            return default
        if resp in choices:
            return resp
        print(f"Please choose one of: {choice_str}")


def _input_int(
    prompt: str,
    default: Optional[int] = None,
    minimum: Optional[int] = None,
    maximum: Optional[int] = None,
) -> int:
    """Prompt for an integer with optional default and bounds."""
    if default is not None:
        full = f"{prompt} (default {default}): "
    else:
        full = prompt + ": "

    while True:
        raw = input(full).strip()
        if not raw and default is not None:
            value = default
        else:
            try:
                value = int(raw)
            except ValueError:
                print("Please enter a whole number.")
                continue

        if minimum is not None and value < minimum:
            print(f"Please enter a value >= {minimum}.")
            continue
        if maximum is not None and value > maximum:
            print(f"Please enter a value <= {maximum}.")
            continue
        return value


def _yes_no(prompt: str, default: bool = True) -> bool:
    """Simple yes/no prompt with default."""
    if default:
        suffix = " [Y/n]: "
    else:
        suffix = " [y/N]: "

    while True:
        resp = input(prompt + suffix).strip().lower()
        if not resp:
            return default
        if resp in ("y", "yes"):
            return True
        if resp in ("n", "no"):
            return False
        print("Please answer 'y' or 'n'.")


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
# Constraint-building helpers
# ---------------------------------------------------------------------------


def _build_suit_range_for_prompt(
    label: str, existing: Optional[SuitRange] = None
) -> SuitRange:
    """Prompt user to define a SuitRange, using existing as defaults if provided."""
    print(f"Define SuitRange for {label}:")
    default_min_cards = existing.min_cards if existing is not None else 0
    default_max_cards = existing.max_cards if existing is not None else 13
    default_min_hcp = existing.min_hcp if existing is not None else 0
    default_max_hcp = existing.max_hcp if existing is not None else 37

    min_cards = _input_int(
        "  Min cards (0–13)",
        default=default_min_cards,
        minimum=0,
        maximum=13,
    )
    max_cards = _input_int(
        "  Max cards (0–13)",
        default=default_max_cards,
        minimum=0,
        maximum=13,
    )
    min_hcp = _input_int(
        "  Min HCP (0–37)",
        default=default_min_hcp,
        minimum=0,
        maximum=37,
    )
    max_hcp = _input_int(
        "  Max HCP (0–37)",
        default=default_max_hcp,
        minimum=0,
        maximum=37,
    )
    try:
        return SuitRange(
            min_cards=min_cards,
            max_cards=max_cards,
            min_hcp=min_hcp,
            max_hcp=max_hcp,
        )
    except ProfileError as exc:
        print(f"  ERROR: {exc}")
        print("  Please re-enter this SuitRange.")
        return _build_suit_range_for_prompt(label, existing)


def _build_standard_constraints(
    existing: Optional[StandardSuitConstraints] = None,
) -> StandardSuitConstraints:
    """
    Interactively define StandardSuitConstraints with total HCP first.

    If existing is provided, use it to populate defaults.
    """
    print("\nStandard constraints for this hand:")

    default_total_min = existing.total_min_hcp if existing is not None else 0
    default_total_max = existing.total_max_hcp if existing is not None else 37

    total_min_hcp = _input_int(
        "  Total min HCP (0–37)",
        default=default_total_min,
        minimum=0,
        maximum=37,
    )
    total_max_hcp = _input_int(
        "  Total max HCP (0–37)",
        default=default_total_max,
        minimum=0,
        maximum=37,
    )

    if total_min_hcp > total_max_hcp:
        print(
            f"  WARNING: total_min_hcp {total_min_hcp} > total_max_hcp {total_max_hcp}. "
            "This will be rejected; please re-enter."
        )
        return _build_standard_constraints(existing)

    print("\nPer-suit constraints (Spades, Hearts, Diamonds, Clubs):")

    sp_existing = existing.spades if existing is not None else None
    h_existing = existing.hearts if existing is not None else None
    d_existing = existing.diamonds if existing is not None else None
    c_existing = existing.clubs if existing is not None else None

    spades = _build_suit_range_for_prompt("Spades", sp_existing)
    hearts = _build_suit_range_for_prompt("Hearts", h_existing)
    diamonds = _build_suit_range_for_prompt("Diamonds", d_existing)
    clubs = _build_suit_range_for_prompt("Clubs", c_existing)

    try:
        return StandardSuitConstraints(
            spades=spades,
            hearts=hearts,
            diamonds=diamonds,
            clubs=clubs,
            total_min_hcp=total_min_hcp,
            total_max_hcp=total_max_hcp,
        )
    except ProfileError as exc:
        print(f"  ERROR: {exc}")
        print("  Please re-enter the standard constraints.")
        return _build_standard_constraints(existing)


def _parse_suit_list(prompt: str, default: Optional[List[str]] = None) -> List[str]:
    """
    Ask the user for a set of suits, e.g. "SHC" or "S H C".

    If default is provided, pressing Enter keeps that default.
    Returns a list like ["S","H","C"].
    """
    while True:
        if default:
            default_str = "".join(default)
            raw = input(
                f"{prompt} (e.g. SHC for Spades, Hearts, Clubs) (default {default_str}): "
            ).strip().upper()
            if not raw:
                return list(default)
        else:
            raw = input(prompt + " (e.g. SHC for Spades, Hearts, Clubs): ").strip().upper()

        chars = [c for c in raw if c in SUITS]
        if not chars:
            print("No valid suits given (must be some of S,H,D,C).")
            continue

        seen = set()
        suits: List[str] = []
        for c in chars:
            if c not in seen:
                seen.add(c)
                suits.append(c)
        return suits


def _build_random_suit_constraint(
    existing: Optional[RandomSuitConstraintData] = None,
) -> RandomSuitConstraintData:
    """Interactively define a RandomSuitConstraintData (with optional defaults)."""
    print("\nRandom Suit constraint:")

    existing_allowed = existing.allowed_suits if existing is not None else None
    allowed_suits = _parse_suit_list("  Allowed suits (any order)", existing_allowed)

    max_count = len(allowed_suits)
    default_required = (
        existing.required_suits_count if existing is not None else 1
    )
    required_suits_count = _input_int(
        "  Number of suits that must meet the random-suit criteria",
        default=default_required,
        minimum=1,
        maximum=max_count,
    )

    # Suit ranges: keep as many as required_suits_count; for editing we
    # reuse existing ranges if present.
    suit_ranges: List[SuitRange] = []
    existing_ranges = existing.suit_ranges if existing is not None else []
    for idx in range(required_suits_count):
        existing_range = existing_ranges[idx] if idx < len(existing_ranges) else None
        sr = _build_suit_range_for_prompt(f"Random Suit #{idx + 1}", existing_range)
        suit_ranges.append(sr)

    # Pair overrides: either keep existing as-is, or rebuild.
    pair_overrides: List[Dict[str, Any]] = []
    existing_overrides = existing.pair_overrides if existing is not None else []

    if existing_overrides:
        print("\n  Existing pair overrides detected:")
        for o in existing_overrides:
            suits = getattr(o, "suits", None) or o.get("suits")
            print(f"    Override for suit pair {suits}")
        if _yes_no("  Keep existing pair overrides?", True):
            pair_overrides = existing_overrides
        else:
            existing_overrides = []  # fall through to rebuild

    if required_suits_count == 2 and not existing_overrides:
        if _yes_no(
            "  Define any specific suit-pair overrides (e.g. D+C special case)?",
            False,
        ):
            while True:
                suits = _parse_suit_list("    Enter exactly two suits for the override")
                if len(suits) != 2:
                    print("    Please choose exactly two suits for the override.")
                    continue
                print(f"    Override for pair {suits[0]} + {suits[1]}:")
                first_range = _build_suit_range_for_prompt("Override first suit")
                second_range = _build_suit_range_for_prompt("Override second suit")
                pair_overrides.append(
                    {
                        "suits": suits,
                        "first_range": first_range,
                        "second_range": second_range,
                    }
                )
                if not _yes_no("    Add another pair override?", False):
                    break

    try:
        return RandomSuitConstraintData(
            required_suits_count=required_suits_count,
            allowed_suits=allowed_suits,
            suit_ranges=suit_ranges,
            pair_overrides=pair_overrides,
        )
    except ProfileError as exc:
        print(f"  ERROR in Random Suit constraint: {exc}")
        print("  Please re-enter the Random Suit constraint.")
        return _build_random_suit_constraint(existing)


def _build_partner_contingent_constraint(
    existing: Optional[PartnerContingentData] = None,
) -> PartnerContingentData:
    """
    Build a PartnerContingentData.

    If existing is provided, use its values as defaults.
    """
    print("\nPartner Contingent constraint:")
    default_partner = existing.partner_seat if existing is not None else "N"
    partner_seat = _input_choice(
        "  Partner seat", ["N", "E", "S", "W"], default_partner
    )

    existing_range = existing.suit_range if existing is not None else None
    suit_range = _build_suit_range_for_prompt("Partner-contingent suit", existing_range)
    return PartnerContingentData(partner_seat=partner_seat, suit_range=suit_range)

def _build_opponent_contingent_constraint(
    existing: Optional[OpponentContingentSuitData] = None,
) -> OpponentContingentSuitData:
    """
    Build an OpponentContingentSuitData.

    If existing is provided, use its values as defaults.
    """
    print("\nOpponent Contingent-Suit constraint:")
    default_opponent = existing.opponent_seat if existing is not None else "E"
    opponent_seat = _input_choice(
        "  Opponent seat", ["N", "E", "S", "W"], default_opponent
    )

    existing_range = existing.suit_range if existing is not None else None
    suit_range = _build_suit_range_for_prompt(
        "Opponent-contingent suit", existing_range
    )
    return OpponentContingentSuitData(
        opponent_seat=opponent_seat,
        suit_range=suit_range,
    )

def _build_subprofile(
    seat: str, existing: Optional[SubProfile] = None
) -> SubProfile:
    """
    Build a single SubProfile for a given seat:
        - StandardSuitConstraints (always)
        - Optionally RandomSuitConstraint, PartnerContingentData,
          or OpponentContingentSuitData

    If existing is provided, its constraints are used as defaults.
    """
    print(f"\nBuilding sub-profile for seat {seat}:")
    existing_std = existing.standard if existing is not None else None
    standard = _build_standard_constraints(existing_std)

    print("\nExtra constraint for this sub-profile:")
    print("  1) None (Standard-only)")
    print("  2) Random Suit constraint")
    print("  3) Partner Contingent constraint")
    print("  4) Opponent Contingent-Suit constraint")

    # Determine default choice based on existing constraint
    if existing is not None:
        if existing.random_suit_constraint is not None:
            default_choice = 2
        elif existing.partner_contingent_constraint is not None:
            default_choice = 3
        elif existing.opponents_contingent_suit_constraint is not None:
            default_choice = 4
        else:
            default_choice = 1
    else:
        default_choice = 1

    choice = _input_int(
        "  Choose [1-4]", default=default_choice, minimum=1, maximum=4
    )

    random_suit_constraint = None
    partner_contingent_constraint = None
    opponents_contingent_suit_constraint = None

    if choice == 1:
        pass
    elif choice == 2:
        existing_rs = existing.random_suit_constraint if existing is not None else None
        random_suit_constraint = _build_random_suit_constraint(existing_rs)
    elif choice == 3:
        existing_pc = (
            existing.partner_contingent_constraint if existing is not None else None
        )
        partner_contingent_constraint = _build_partner_contingent_constraint(
            existing_pc
        )
    else:
        existing_oc = (
            existing.opponents_contingent_suit_constraint
            if existing is not None
            else None
        )
        opponents_contingent_suit_constraint = _build_opponent_contingent_constraint(
            existing_oc
        )

    return SubProfile(
        standard=standard,
        random_suit_constraint=random_suit_constraint,
        partner_contingent_constraint=partner_contingent_constraint,
        opponents_contingent_suit_constraint=opponents_contingent_suit_constraint,
    )

def _build_seat_profile(
    seat: str, existing: Optional[SeatProfile] = None
) -> SeatProfile:
    """
    Build SeatProfile with one or more SubProfiles.

    If existing is provided, number of sub-profiles and their constraints
    are used as defaults.
    """
    print(f"\n--- Seat {seat} ---")
    existing_subs = existing.subprofiles if existing is not None else []
    default_num = len(existing_subs) if existing_subs else 1

    num_sub = _input_int(
        f"How many sub-profiles for seat {seat}?",
        default=default_num,
        minimum=1,
        maximum=6,
    )

    subs: List[SubProfile] = []
    for idx in range(1, num_sub + 1):
        print(f"\nSub-profile {idx} for seat {seat}:")
        existing_sub = existing_subs[idx - 1] if idx - 1 < len(existing_subs) else None
        sub = _build_subprofile(seat, existing_sub)
        subs.append(sub)

    return SeatProfile(seat=seat, subprofiles=subs)


# ---------------------------------------------------------------------------
# Profile creation / rebuilding / constraint editing
# ---------------------------------------------------------------------------


def create_profile_interactive(existing: Optional[HandProfile] = None) -> HandProfile:
    """
    Interactive builder for a full HandProfile.

    If 'existing' is provided, its metadata are used as defaults, but
    constraints are built from scratch.
    """
    print("\n=== Create / Rebuild Profile ===")

    if existing is not None:
        default_name = existing.profile_name
        default_desc = existing.description
        default_tag = existing.tag
        default_dealer = existing.dealer
        default_author = getattr(existing, "author", "")
        default_version = getattr(existing, "version", "")
    else:
        default_name = "New Profile"
        default_desc = ""
        default_tag = "Opener"
        default_dealer = "N"
        default_author = "Lee"
        default_version = "0.1"

    profile_name = _input_with_default("Profile name", default_name)
    description = _input_with_default("Description", default_desc)
    tag = (
        _input_choice(
            "Tag (Opener / Overcaller)",
            ["OPENER", "OVERCALLER"],
            default_tag.upper(),
        )
        .capitalize()
    )
    dealer = _input_choice("Dealer seat", ["N", "E", "S", "W"], default_dealer)
    author = _input_with_default("Author", default_author or "Lee")
    version = _input_with_default("Version", default_version or "0.1")

    # Deal order: start at dealer, then clockwise
    print("\nHand dealing order:")
    print("By default we deal clockwise starting from the dealer.")
    default_order = [dealer]
    clockwise = ["N", "E", "S", "W"]
    start_index = clockwise.index(dealer)
    for i in range(1, 4):
        default_order.append(clockwise[(start_index + i) % 4])

    print(f"Default dealing order: {default_order}")
    if _yes_no("Use this dealing order?", True):
        hand_dealing_order = default_order
    else:
        # Allow custom order as long as it's a permutation of N,E,S,W
        while True:
            raw = input(
                "Enter dealing order as 4 seats separated by spaces (e.g. N E S W): "
            ).strip().upper()
            parts = raw.split()
            if len(parts) != 4:
                print("Please enter exactly 4 seats.")
                continue
            if set(parts) != set(["N", "E", "S", "W"]):
                print("Must be a permutation of N,E,S,W.")
                continue
            if parts[0] != dealer:
                print("First seat must be the dealer.")
                continue
            hand_dealing_order = parts
            break

    # Build SeatProfiles in dealing order
    seat_profiles: Dict[str, SeatProfile] = {}
    for seat in hand_dealing_order:
        seat_profiles[seat] = _build_seat_profile(seat)

    profile = HandProfile(
        profile_name=profile_name,
        description=description,
        dealer=dealer,
        hand_dealing_order=hand_dealing_order,
        tag=tag,
        seat_profiles=seat_profiles,
        author=author,
        version=version,
    )

    # Run full validation
    validate_profile(profile)
    return profile


def edit_constraints_interactive(existing: HandProfile) -> HandProfile:
    print("\n=== Edit Constraints for Profile ===")
    print(f"Profile: {existing.profile_name}")
    print(f"Dealer : {existing.dealer}")
    print(f"Order  : {existing.hand_dealing_order}")

    hand_dealing_order = list(existing.hand_dealing_order)
    seat_profiles: Dict[str, SeatProfile] = {}

    for seat in hand_dealing_order:
        print(f"\n--- Editing constraints for seat {seat} ---")
        existing_seat_profile = existing.seat_profiles[seat]

        if not _yes_no(f"Do you want to edit constraints for seat {seat}?", True):
            seat_profiles[seat] = existing_seat_profile
            continue

        new_seat_profile = _build_seat_profile(seat, existing_seat_profile)
        seat_profiles[seat] = new_seat_profile

    updated = HandProfile(
        profile_name=existing.profile_name,
        description=existing.description,
        dealer=existing.dealer,
        hand_dealing_order=hand_dealing_order,
        tag=existing.tag,
        seat_profiles=seat_profiles,
        author=getattr(existing, "author", ""),
        version=getattr(existing, "version", ""),
    )

    validate_profile(updated)
    return updated


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

    choice = _input_int("Choose profile number (0 to cancel)", default=0, minimum=0)
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
    if _yes_no("Save this new profile?", True):
        path = _profile_path_for(profile)
        _save_profile_to_path(profile, path)


def _print_suit_range(label: str, r: SuitRange, indent: str = "") -> None:
    print(
        f"{indent}{label}: cards {r.min_cards}–{r.max_cards}, "
        f"HCP {r.min_hcp}–{r.max_hcp}"
    )


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
    print(f"{indent}Random Suit constraint:")
    print(f"{indent}  Allowed suits         : {''.join(rs.allowed_suits)}")
    print(
        f"{indent}  Required suits count  : {rs.required_suits_count}"
    )
    for idx, r in enumerate(rs.suit_ranges, start=1):
        _print_suit_range(f"Random Suit #{idx}", r, indent + "  ")
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
            print(f"{indent}    Pair: {suits}")
            if first_range is not None:
                _print_suit_range("First suit", first_range, indent + "      ")
            if second_range is not None:
                _print_suit_range("Second suit", second_range, indent + "      ")


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

def _print_full_profile_details(profile: HandProfile, path: Path) -> None:
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

    print("\nSeat profiles (in dealing order):")
    for seat in profile.hand_dealing_order:
        sp = profile.seat_profiles.get(seat)
        if sp is None:
            continue
        print(f"\n--- Seat {seat} ---")
        print(f"Number of sub-profiles: {len(sp.subprofiles)}")
        for idx, sub in enumerate(sp.subprofiles, start=1):
            print(f"\n  Sub-profile {idx}:")
            print("    Standard constraints:")
            _print_standard_constraints(sub.standard, indent="      ")

            if sub.random_suit_constraint is not None:
                _print_random_suit_constraint(sub.random_suit_constraint, indent="    ")

            if sub.partner_contingent_constraint is not None:
                _print_partner_contingent_constraint(
                    sub.partner_contingent_constraint, indent="    "
                )
            if getattr(sub, "opponents_contingent_suit_constraint", None) is not None:
                _print_opponent_contingent_constraint(
                    sub.opponents_contingent_suit_constraint, indent="    "
                )

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

    # Offer to print full constraints
    if _yes_no("\nPrint full profile details including constraints?", False):
        _print_full_profile_details(profile, path)


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
            _input_choice(
                "Tag (Opener / Overcaller)",
                ["OPENER", "OVERCALLER"],
                profile.tag.upper(),
            )
            .capitalize()
        )
        new_dealer = _input_choice(
            "Dealer seat", ["N", "E", "S", "W"], profile.dealer
        )

        # Edit hand dealing order (must be a permutation of N,E,S,W starting with dealer)
        current_order = profile.hand_dealing_order
        default_order_str = " ".join(current_order)
        print(f"Current hand dealing order: {current_order}")
        while True:
            raw_order = _input_with_default(
                "Hand dealing order (4 seats, e.g. 'W N S E')",
                default_order_str,
            )
            parts = raw_order.replace(",", " ").upper().split()
            if len(parts) != 4 or set(parts) != {"N", "E", "S", "W"}:
                print("  ERROR: please enter each of N, E, S, W exactly once.")
                continue
            if parts[0] != new_dealer:
                print(
                    f"  ERROR: dealing order must start with the dealer ({new_dealer})."
                )
                continue
            new_hand_dealing_order = parts
            break

        new_author = _input_with_default(
            "Author", getattr(profile, "author", "") or "Lee"
        )
        new_version = _input_with_default(
            "Version", getattr(profile, "version", "") or "0.1"
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
        )

        # Validate
        validate_profile(updated)

        if _yes_no("Save changes to this profile?", True):
            new_path = _profile_path_for(updated)
            _save_profile_to_path(updated, new_path)
        return

    # Constraints-only edit
    try:
        updated = edit_constraints_interactive(profile)
    except ProfileError as exc:
        print(f"ERROR while editing constraints: {exc}")
        return

    if _yes_no("Save updated constraints to this profile?", True):
        new_path = _profile_path_for(updated)
        _save_profile_to_path(updated, new_path)


def delete_profile_action() -> None:
    profiles = _load_profiles()
    chosen = _choose_profile(profiles)
    if chosen is None:
        return
    path, profile = chosen
    if _yes_no(f"Really delete profile '{profile.profile_name}'?", False):
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
            create_profile_action()
        elif choice == 3:
            view_and_optional_print_profile_action()
        elif choice == 4:
            edit_profile_action()
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