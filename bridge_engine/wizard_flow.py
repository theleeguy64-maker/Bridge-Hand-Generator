"""
Interactive wizard helpers for building and editing HandProfile objects.

This module centralises the interactive, prompt-driven construction of
profiles so that both the CLI and tests can rely on a single behaviour.
"""

# TEST CONTRACT — wizard_flow.py (tests monkeypatch via profile_wizard facade)
#
# The following symbols are intentionally monkeypatched by tests and must remain
# defined at module scope. Do not rename or remove without updating tests.
#
# Prompt wrappers (tests control interactive behavior):
#   - _input_with_default(prompt: str, default: str) -> str
#   - _input_int(prompt, default, minimum, maximum, show_range_suffix=True) -> int
#   - _yes_no(prompt: str, default: bool = True) -> bool
#   - _yes_no_help(prompt: str, help_key: str, default: bool = True) -> bool
#   - clear_screen()
#
# Builder / flow helpers patched by tests:
#   - _build_seat_profile(seat: str)
#   - _build_profile(existing: Optional[HandProfile] = None)
#   - edit_constraints_interactive(existing: HandProfile)
#
# Injection points:
#   - HandProfile
#   - validate_profile
#
# Behavioral guarantees relied on by tests:
#   - rotate_deals_by_default is passed into HandProfile(...)
#   - Accepting defaults bypasses optional prompts
#
# If you refactor internals, preserve these names or update tests accordingly.

# file: bridge_engine/wizard_flow.py

from __future__ import annotations

import sys

from dataclasses import replace
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .menu_help import get_menu_help
from . import wizard_io as wiz_io
from .cli_prompts import (
    prompt_int,
)

from .hand_profile_model import _default_dealing_order


# NOTE: pytest monkeypatches input helpers on bridge_engine.profile_wizard.
# After splitting the wizard into modules, we route interactive I/O through
# that module when available (falling back to wizard_io). This preserves the
# stable monkeypatch seam expected by tests.
def _pw_attr(name: str, fallback: Any) -> Any:
    """
    Late attribute lookup on the already-imported profile_wizard module.
    This preserves monkeypatch seams even if imports happen in different order.
    """
    pw = sys.modules.get("bridge_engine.profile_wizard")
    if pw is None:
        try:
            from . import profile_wizard as pw  # local import avoids cycles at import time
        except ImportError:
            return fallback

    return getattr(pw, name, fallback)


def _yes_no(prompt: str, default: bool = True) -> bool:
    return _pw_attr("_yes_no", wiz_io._yes_no)(prompt, default=default)


def _yes_no_help(prompt: str, help_key: str, default: bool = True) -> bool:
    """Yes/no with inline help — routes through _pw_attr for monkeypatch seam."""
    return _pw_attr("_yes_no_help", wiz_io._yes_no_help)(prompt, help_key, default=default)


def _prompt_yne(prompt: str, default: str = "y") -> str:
    """Prompt for y/n/e — routes through _pw_attr for monkeypatch seam."""
    return _pw_attr("_prompt_yne", wiz_io._prompt_yne)(prompt, default=default)


def _input_with_default(prompt: str, default: str) -> str:
    return _pw_attr("_input_with_default", wiz_io._input_with_default)(prompt, default)


def _input_int(prompt: str, default: int, minimum: int, maximum: int, show_range_suffix: bool = True) -> int:
    return _pw_attr("_input_int", wiz_io._input_int)(
        prompt, default=default, minimum=minimum, maximum=maximum, show_range_suffix=show_range_suffix
    )


def _input_choice(
    prompt: str,
    options: Sequence[str],
    default: Optional[str] = None,
) -> str:
    """
    Prompt the user to choose from options.

    - Case-insensitive input (e.g. 'w' → 'W')
    - Returns the canonical option string from `options`.
    """
    if not options:
        raise ValueError("_input_choice requires at least one option")

    # Build a map from normalised key -> canonical option
    norm_map = {opt.upper(): opt for opt in options}
    default_norm = default.upper() if default is not None else None

    options_str = "/".join(options)
    while True:
        raw = wiz_io.prompt_str(
            f"{prompt} ({options_str})" + (f" [{default}]" if default is not None else "") + ": ",
            default=default if default is not None else "",
        )
        key = raw.strip().upper()

        # Empty input → default (if any) or first option
        if not key:
            if default_norm is not None and default_norm in norm_map:
                return norm_map[default_norm]
            return options[0]

        if key in norm_map:
            return norm_map[key]

        print(f"Please enter one of: {options_str}")


def _input_float_with_default(
    prompt: str,
    default: float,
    *,
    min_value: float = 0.0,
    max_value: float = 100.0,
    decimal_places: int = 2,
) -> float:
    """
    Prompt for a float with a default and optional min/max bounds.

    Accepts keyword arguments min_value / max_value so that existing call
    sites like _input_float_with_default(..., min_value=0.0, max_value=100.0)
    continue to work.

    decimal_places controls rounding of the returned value (default 2).

    Returns a validated, rounded float.
    """
    while True:
        raw = _input_with_default(prompt, str(default))

        # Allow empty → default, in case callers bypass _input_with_default
        if raw.strip() == "":
            return round(default, decimal_places)

        try:
            value = float(raw)
        except ValueError:
            print("Please enter a numeric value.")
            continue

        if value < min_value or value > max_value:
            print(f"Please enter a value between {min_value} and {max_value}.")
            continue

        return round(value, decimal_places)


def clear_screen() -> None:
    return _pw_attr("clear_screen", wiz_io.clear_screen)()


from .hand_profile import (
    HandProfile,
    OpponentContingentSuitData,
    PartnerContingentData,
    RandomSuitConstraintData,
    SeatProfile,
    StandardSuitConstraints,
    SubProfile,
    SubprofileExclusionClause,
    SubprofileExclusionData,
    SuitRange,
    sub_label,
    validate_profile,
)


# ---------------------------------------------------------------------------
# Sub-profile exclusions (F2) — wizard helpers
# ---------------------------------------------------------------------------


def _parse_shapes_csv(raw: str) -> List[str]:
    shapes: List[str] = []
    for part in raw.split(","):
        s = part.strip()
        if not s:
            continue
        shapes.append(s)
    return shapes


def _build_exclusion_rule(
    seat: str,
    subprofile_index: int,
    kind: str = "",
) -> SubprofileExclusionData:
    # If kind not provided, prompt for it (standalone/fallback usage)
    if not kind:
        kind = _input_choice(
            "Exclusion type (shapes=exact 4-digit patterns, rule=ANY/MAJOR/MINOR clauses)",
            options=["shapes", "rule"],
            default="shapes",
        )

    if kind == "shapes":
        raw = _input_with_default(
            "Enter excluded shapes as comma-separated 4-digit S/H/D/C patterns (e.g. 4333, 64xx where x=any): ",
            "",
        ).strip()
        shapes = _parse_shapes_csv(raw)
        return SubprofileExclusionData(
            seat=seat,
            subprofile_index=subprofile_index,
            excluded_shapes=shapes,
            clauses=None,
        )

    # kind == "rule"
    clauses: List[SubprofileExclusionClause] = []
    max_clauses = 2
    for idx in range(1, max_clauses + 1):
        group = _input_choice(
            f"Clause {idx}: group",
            options=["ANY", "MAJOR", "MINOR"],
            default="MAJOR" if idx == 1 else "MINOR",
        )
        length_eq = _input_int(
            f"Clause {idx}: length_eq (0–13)",
            default=0,
            minimum=0,
            maximum=13,
        )
        max_count = 4 if group == "ANY" else 2
        count = _input_int(
            f"Clause {idx}: count (0–{max_count})",
            default=1,
            minimum=0,
            maximum=max_count,
        )
        clauses.append(SubprofileExclusionClause(group=group, length_eq=length_eq, count=count))

        if idx < max_clauses and not _yes_no("Add a second clause? ", default=False):
            break

    return SubprofileExclusionData(
        seat=seat,
        subprofile_index=subprofile_index,
        excluded_shapes=None,
        clauses=clauses,
    )


def _print_exclusion_summary(exc: SubprofileExclusionData, sp: SeatProfile) -> None:
    """Print a confirmation summary of a newly added exclusion."""
    si = exc.subprofile_index  # 1-based
    label = sub_label(si, sp.subprofiles[si - 1]) if 1 <= si <= len(sp.subprofiles) else f"Sub-profile {si}"
    if exc.excluded_shapes:
        shapes_txt = ", ".join(str(s) for s in exc.excluded_shapes)
        print(f"  Added: {label}: exclude shapes: {shapes_txt}")
    elif exc.clauses:
        parts = [f"({c.group} len={c.length_eq} count={c.count})" for c in exc.clauses]
        print(f"  Added: {label}: exclude if: " + " AND ".join(parts))


def _print_exclusions_for_subprofile(
    sub_excls: List[SubprofileExclusionData],
    label: str,
) -> None:
    """Print exclusions belonging to one subprofile, or '(none)'."""
    if not sub_excls:
        print(f"  {label}: (none)")
        return
    print(f"  {label}:")
    for i, exc in enumerate(sub_excls, start=1):
        if exc.excluded_shapes:
            shapes_txt = ", ".join(str(s) for s in exc.excluded_shapes)
            print(f"    {i}) exclude shapes: {shapes_txt}")
        elif exc.clauses:
            parts = [f"({c.group} len={c.length_eq} count={c.count})" for c in exc.clauses]
            print(f"    {i}) exclude if: " + " AND ".join(parts))
        else:
            print(f"    {i}) (invalid exclusion)")


def _edit_exclusions_for_subprofile(
    seat: str,
    sub_idx: int,
    sp: SeatProfile,
    this_sub_excls: List[SubprofileExclusionData],
) -> List[SubprofileExclusionData]:
    """
    Edit exclusions for ONE subprofile (inner menu only, no sub-picker).

    Parameters:
        seat:           The seat letter (N/E/S/W).
        sub_idx:        1-based subprofile index.
        sp:             The SeatProfile (used for label display).
        this_sub_excls: Current exclusions for this subprofile (mutable copy).

    Returns the updated exclusion list for this subprofile.
    """
    label = sub_label(sub_idx, sp.subprofiles[sub_idx - 1])

    print()  # Visual separator before exclusion gate prompt

    # Gate prompt: ask whether to add/edit exclusions for this subprofile
    has_existing = len(this_sub_excls) > 0
    if not _yes_no_help(
        f"Add/edit exclusions for {label}?",
        "yn_exclusions",
        default=has_existing,
    ):
        return this_sub_excls

    # Show current exclusions before the menu
    _print_exclusions_for_subprofile(this_sub_excls, label)

    # Inner loop: unified menu for this subprofile
    while True:
        sub_excls = list(this_sub_excls)
        has_excls = len(sub_excls) > 0

        print(f"\nExclusion menu for seat {seat}, {label}:")
        print("  0) Exit")
        print("  1) Add shapes exclusion")
        print("  2) Add rule exclusion")
        if has_excls:
            print("  3) Remove exclusion")
            print("  4) Help")
            max_choice = 4
        else:
            print("  3) Help")
            max_choice = 3

        choice = _input_int("Choice", default=0, minimum=0, maximum=max_choice)

        if choice == 0:
            break
        elif choice == 1:
            exc = _build_exclusion_rule(seat=seat, subprofile_index=sub_idx, kind="shapes")
            this_sub_excls.append(exc)
            _print_exclusion_summary(exc, sp)
        elif choice == 2:
            exc = _build_exclusion_rule(seat=seat, subprofile_index=sub_idx, kind="rule")
            this_sub_excls.append(exc)
            _print_exclusion_summary(exc, sp)
        elif choice == 3 and has_excls:
            # Show numbered list for removal
            for ri, re_exc in enumerate(sub_excls, start=1):
                if re_exc.excluded_shapes:
                    shapes_txt = ", ".join(str(s) for s in re_exc.excluded_shapes)
                    print(f"  {ri}) exclude shapes: {shapes_txt}")
                elif re_exc.clauses:
                    parts = [f"({c.group} len={c.length_eq} count={c.count})" for c in re_exc.clauses]
                    print(f"  {ri}) exclude if: " + " AND ".join(parts))
            n = _input_int(
                f"Which exclusion # to remove (1–{len(sub_excls)})",
                default=1,
                minimum=1,
                maximum=len(sub_excls),
            )
            # Remove from this_sub_excls by identity
            this_sub_excls.remove(sub_excls[n - 1])
            print("  Removed.")
        else:
            # Help (choice 3 when no excls, or choice 4 when excls present)
            print(get_menu_help("exclusions"))

    return this_sub_excls


def _edit_subprofile_exclusions_for_seat(
    *,
    existing: Optional[HandProfile],
    seat: str,
    seat_profiles: Dict[str, SeatProfile],
    current_all: List[SubprofileExclusionData],
) -> List[SubprofileExclusionData]:
    """
    Legacy wrapper — edit exclusions for ONE seat via sub-picker loop.

    This is kept for backward compatibility with tests that call it directly.
    The main wizard flow now uses _edit_exclusions_for_subprofile() per-sub
    inside _build_seat_profile().
    """
    # Partition: this seat vs other seats
    this_seat = [e for e in current_all if e.seat == seat]
    other = [e for e in current_all if e.seat != seat]

    sp = seat_profiles.get(seat)
    if sp is None or not sp.subprofiles:
        print(f"(No sub-profiles for seat {seat}; exclusions not applicable.)")
        return current_all

    # If no existing for this seat, optionally skip
    default_edit = True if this_seat else False
    if not _yes_no_help(
        f"Add/edit sub-profile exclusions for seat {seat}?",
        "yn_exclusions",
        default=default_edit,
    ):
        return current_all

    # Outer loop: pick a subprofile to work on (0 = done)
    while True:
        # Show current exclusions grouped by subprofile before each prompt
        print(f"\nExisting exclusions for seat {seat}:")
        for si, sub in enumerate(sp.subprofiles, start=1):
            lbl = sub_label(si, sub)
            sub_excls = [e for e in this_seat if e.subprofile_index == si]
            _print_exclusions_for_subprofile(sub_excls, lbl)

        sub_idx = _input_int(
            f"\nSubprofile number for seat {seat} to edit (0=done, 1–{len(sp.subprofiles)})",
            default=0,
            minimum=0,
            maximum=len(sp.subprofiles),
        )
        if sub_idx == 0:
            break

        # Delegate to the per-subprofile menu
        sub_excls_for_idx = [e for e in this_seat if e.subprofile_index == sub_idx]
        # Remove old ones from this_seat, replace with updated
        this_seat = [e for e in this_seat if e.subprofile_index != sub_idx]
        updated = _edit_exclusions_for_subprofile(
            seat=seat,
            sub_idx=sub_idx,
            sp=sp,
            this_sub_excls=sub_excls_for_idx,
        )
        this_seat.extend(updated)

    return other + this_seat


# NEW: helper for auto-standard constraints on brand-new profiles
def _make_default_standard_seat_profile(seat: str) -> SeatProfile:
    """
    Build a simple 'all-open' standard SeatProfile with a single sub-profile.

    Used when creating a brand-new profile: user supplies only metadata and
    we attach standard constraints automatically.

    Defaults mirror the interactive wizard's defaults:
      - Total HCP: 0–37
      - Per suit: 0–6 cards, 0–10 HCP
      - No random / partner / opponent constraints
      - Weighting: left at 0.0; validate_profile() will normalise to 100%
      - NS seats default ns_role_usage to 'any'
    """
    std = StandardSuitConstraints(
        total_min_hcp=0,
        total_max_hcp=37,
        spades=SuitRange(min_cards=0, max_cards=6, min_hcp=0, max_hcp=10),
        hearts=SuitRange(min_cards=0, max_cards=6, min_hcp=0, max_hcp=10),
        diamonds=SuitRange(min_cards=0, max_cards=6, min_hcp=0, max_hcp=10),
        clubs=SuitRange(min_cards=0, max_cards=6, min_hcp=0, max_hcp=10),
    )

    sub = SubProfile(
        standard=std,
    )

    return SeatProfile(seat=seat, subprofiles=[sub])


def _build_suit_range_for_prompt(
    label: str,
    existing: Optional[SuitRange] = None,
    *,
    default_min_cards: Optional[int] = None,
    default_max_cards: Optional[int] = None,
    default_min_hcp: Optional[int] = None,
    default_max_hcp: Optional[int] = None,
) -> SuitRange:
    """
    Interactively build a SuitRange for the given label.

    Backwards-compatible:
      - tests call: _build_suit_range_for_prompt("Spades")
      - standard constraints call: _build_suit_range_for_prompt(label, existing)
      - random-suit builder can pass explicit defaults via keyword-only args.
    """
    print(f"Define SuitRange for {label}:")

    # Base defaults
    if existing is not None:
        min_cards = existing.min_cards
        max_cards = existing.max_cards
        min_hcp = existing.min_hcp
        max_hcp = existing.max_hcp
    else:
        # Defaults expected by tests for a fresh SuitRange
        min_cards = 0
        max_cards = 6
        min_hcp = 0
        max_hcp = 10

    # Allow explicit overrides from keyword-only args
    if default_min_cards is not None:
        min_cards = default_min_cards
    if default_max_cards is not None:
        max_cards = default_max_cards
    if default_min_hcp is not None:
        min_hcp = default_min_hcp
    if default_max_hcp is not None:
        max_hcp = default_max_hcp

    # All calls in tests expect show_range_suffix=False here
    min_cards_val = _input_int(
        "  Min cards (0–13)",
        default=min_cards,
        minimum=0,
        maximum=13,
        show_range_suffix=False,
    )
    max_cards_val = _input_int(
        "  Max cards (0–13)",
        default=max_cards,
        minimum=0,
        maximum=13,
        show_range_suffix=False,
    )
    min_hcp_val = _input_int(
        "  Min HCP (0–10)",
        default=min_hcp,
        minimum=0,
        maximum=10,
        show_range_suffix=False,
    )
    max_hcp_val = _input_int(
        "  Max HCP (0–10)",
        default=max_hcp,
        minimum=0,
        maximum=10,
        show_range_suffix=False,
    )

    return SuitRange(
        min_cards=min_cards_val,
        max_cards=max_cards_val,
        min_hcp=min_hcp_val,
        max_hcp=max_hcp_val,
    )


def _parse_suit_list(
    prompt: str,
    default: Optional[Sequence[str]] = None,
) -> List[str]:
    """
    Parse a short string of suit letters like 'SHC' into a list of unique suits.

    `prompt` should be the full prompt text to show to the user (including
    any '(default ...)' text). If the user just presses ENTER and a default
    is provided, we return the default.
    """
    default_list: List[str] = list(default) if default is not None else []
    # Route through wiz_io so tests can monkeypatch input.
    raw = wiz_io.prompt_str(prompt, default="").strip().upper()

    if not raw:
        # No input: fall back to default if given, otherwise all suits.
        if default_list:
            return default_list
        return ["S", "H", "D", "C"]

    suits: List[str] = []
    for ch in raw:
        if ch in ("S", "H", "D", "C") and ch not in suits:
            suits.append(ch)

    if not suits:
        # If they typed junk, fall back to default or to all suits.
        if default_list:
            return default_list
        return ["S", "H", "D", "C"]

    return suits


def _build_standard_constraints(
    existing: Optional[StandardSuitConstraints] = None,
    label_suffix: str = "",
) -> StandardSuitConstraints:
    """
    Interactively define StandardSuitConstraints with total HCP first.

    If existing is provided, use it to populate defaults.

    Tests assert that the total HCP prompts do *not* show the range suffix;
    they also sometimes call this with a second `label_suffix` argument,
    so we keep it in the signature (default empty).
    """
    print("\nStandard constraints for this hand:")

    # Defaults for total HCP
    default_total_min = existing.total_min_hcp if existing else 0
    default_total_max = existing.total_max_hcp if existing else 37

    # NOTE: tests expect show_range_suffix=False for totals.
    total_min = _input_int(
        f"  Total min HCP (0–37){label_suffix}",
        default=default_total_min,
        minimum=0,
        maximum=37,
        show_range_suffix=False,
    )
    total_max = _input_int(
        f"  Total max HCP (0–37){label_suffix}",
        default=default_total_max,
        minimum=0,
        maximum=37,
        show_range_suffix=False,
    )

    # Per-suit details
    print("\nPer-suit constraints (Spades, Hearts, Diamonds, Clubs):")

    # Extract per-suit ranges from existing constraints if editing
    existing_spades = existing.spades if existing is not None else None
    existing_hearts = existing.hearts if existing is not None else None
    existing_diamonds = existing.diamonds if existing is not None else None
    existing_clubs = existing.clubs if existing is not None else None

    spades = _build_suit_range_for_prompt("Spades", existing_spades)
    hearts = _build_suit_range_for_prompt("Hearts", existing_hearts)
    diamonds = _build_suit_range_for_prompt("Diamonds", existing_diamonds)
    clubs = _build_suit_range_for_prompt("Clubs", existing_clubs)

    return StandardSuitConstraints(
        spades=spades,
        hearts=hearts,
        diamonds=diamonds,
        clubs=clubs,
        total_min_hcp=total_min,
        total_max_hcp=total_max,
    )


def _prompt_suit_range(
    suit_name: str,
    existing: Optional[SuitRange] = None,
) -> SuitRange:
    """
    Prompt the user to define a SuitRange for one suit.
    """
    print(f"Define SuitRange for {suit_name}:")
    if existing is None:
        default_min_cards = 0
        default_max_cards = 13
        default_min_hcp = 0
        default_max_hcp = 10
    else:
        default_min_cards = existing.min_cards
        default_max_cards = existing.max_cards
        default_min_hcp = existing.min_hcp
        default_max_hcp = existing.max_hcp

    min_cards = prompt_int(
        "  Min cards",
        default_min_cards,
        0,
        13,
    )
    max_cards = prompt_int(
        "  Max cards",
        default_max_cards,
        0,
        13,
    )
    min_hcp = prompt_int(
        "  Min HCP",
        default_min_hcp,
        0,
        10,
    )
    max_hcp = prompt_int(
        "  Max HCP",
        default_max_hcp,
        0,
        10,
    )
    return SuitRange(
        min_cards=min_cards,
        max_cards=max_cards,
        min_hcp=min_hcp,
        max_hcp=max_hcp,
    )


def _build_partner_contingent_constraint(
    existing: Optional[PartnerContingentData] = None,
) -> PartnerContingentData:
    """
    Build / edit a Partner Contingent constraint.
    """
    print("\nPartner Contingent constraint:")

    default_partner_seat = existing.partner_seat if existing else "N"
    partner_seat = _input_choice(
        "Partner seat [N/E/S/W]: ",
        ["N", "E", "S", "W"],
        default_partner_seat,
    )

    # Ask whether to target the partner's chosen or unchosen RS suit
    # BEFORE prompting for suit range, so the user knows which variant
    # they are defining ranges for.
    default_choice = "U" if (existing is not None and existing.use_non_chosen_suit) else "C"
    while True:
        raw = (
            _input_with_default(
                "  Target partner's CHOSEN or UNCHOSEN RS suit? (C/U)",
                default_choice,
            )
            .strip()
            .upper()
        )
        if raw == "?":
            print(get_menu_help("yn_non_chosen_partner"))
            continue
        if raw.startswith("U"):
            use_non_chosen = True
            break
        if raw.startswith("C"):
            use_non_chosen = False
            break
        print("  Please enter C (chosen) or U (unchosen).")

    # Extract existing suit range if editing an existing constraint.
    existing_suit_range = existing.suit_range if existing is not None else None

    suit_range = _prompt_suit_range("Partner suit", existing_suit_range)

    return PartnerContingentData(
        partner_seat=partner_seat,
        suit_range=suit_range,
        use_non_chosen_suit=use_non_chosen,
    )


def _build_opponent_contingent_constraint(
    existing: Optional[OpponentContingentSuitData] = None,
) -> Optional[OpponentContingentSuitData]:
    """
    Build / edit an Opponent Contingent-Suit constraint.

    This mirrors the partner-contingent flow, but targets an opponent seat and a SuitRange.
    """
    print("\nOpponent Contingent-Suit constraint:")

    want = _yes_no(
        "Add / edit opponent contingent-suit constraint? ",
        default=(existing is not None),
    )
    if not want:
        return existing if existing is not None else None

    default_opp = existing.opponent_seat if existing is not None else "E"
    opponent_seat = _input_choice(
        "Opponent seat (N/E/S/W)",
        options=["N", "E", "S", "W"],
        default=default_opp,
    )

    # Ask whether to target the opponent's chosen or unchosen RS suit
    # BEFORE prompting for suit range, so the user knows which variant
    # they are defining ranges for.
    # E.g., if opponent RS picks H from [S, H], unchosen mode means
    # this seat's OC constraint applies to S instead of H.
    default_choice = "U" if (existing is not None and existing.use_non_chosen_suit) else "C"
    while True:
        raw = (
            _input_with_default(
                "  Target opponent's CHOSEN or UNCHOSEN RS suit? (C/U)",
                default_choice,
            )
            .strip()
            .upper()
        )
        if raw == "?":
            print(get_menu_help("yn_non_chosen_opponent"))
            continue
        if raw.startswith("U"):
            use_non_chosen = True
            break
        if raw.startswith("C"):
            use_non_chosen = False
            break
        print("  Please enter C (chosen) or U (unchosen).")

    # Use the same SuitRange prompt helper used elsewhere in this wizard.
    suit_range = _prompt_suit_range(
        "Suit",
        existing.suit_range if existing is not None else None,
    )

    return OpponentContingentSuitData(
        opponent_seat=opponent_seat,
        suit_range=suit_range,
        use_non_chosen_suit=use_non_chosen,
    )


def _build_random_suit_constraint(
    existing: Optional[RandomSuitConstraintData] = None,
) -> RandomSuitConstraintData:
    """
    Interactive builder for RandomSuitConstraintData.

    Uses the new dataclass fields:
      - required_suits_count: int
      - allowed_suits: List[str]
      - suit_ranges: List[SuitRange]
      - pair_overrides: List[SuitPairOverride]
    """
    print("\nRandom Suit constraint:")

    # ----- Allowed suits -----
    if existing is not None and existing.allowed_suits:
        default_allowed = list(existing.allowed_suits)
    else:
        # Original default for this profile: SH
        default_allowed = ["S", "H"]

    default_allowed_str = "".join(default_allowed)

    allowed_suits = _parse_suit_list(
        f"  Allowed suits (any order) (e.g. SHC for Spades, Hearts, Clubs) (default {default_allowed_str}): ",
        default=default_allowed,
    )

    # ----- How many suits must satisfy the constraint? -----
    if existing is not None:
        default_required = existing.required_suits_count
    else:
        default_required = 1

    # For now we cap at 2 suits, matching your UI text (>=1 and <=2).
    max_required = min(2, len(allowed_suits)) if allowed_suits else 2

    num_required = _input_int(
        "  Number of suits that must meet the random-suit criteria",
        default=default_required,
        minimum=1,
        maximum=max_required,
        show_range_suffix=False,
    )

    # ----- Per-suit ranges for the random suits -----
    existing_ranges = existing.suit_ranges if existing is not None else []
    suit_ranges: List[SuitRange] = []

    for idx in range(num_required):
        label = f"Random Suit #{idx + 1}"
        existing_range = existing_ranges[idx] if idx < len(existing_ranges) else None

        sr = _build_suit_range_for_prompt(label, existing_range)
        suit_ranges.append(sr)

    # Keep any existing pair_overrides, or default to empty list
    pair_overrides = list(existing.pair_overrides) if existing else []

    return RandomSuitConstraintData(
        allowed_suits=allowed_suits,
        required_suits_count=num_required,
        suit_ranges=suit_ranges,
        pair_overrides=pair_overrides,
    )


def _build_subprofile(
    seat: str,
    existing: Optional[SubProfile] = None,
) -> SubProfile:
    """
    Interactive builder for a single SubProfile for a given seat.

    If `existing` is provided, it is used to pre-fill defaults where possible.
    """
    print(f"\nBuilding sub-profile for seat {seat}:")

    # Optional name for this sub-profile (purely cosmetic label).
    existing_name = existing.name if existing is not None else ""
    default_hint = f" [{existing_name}]" if existing_name else ""
    raw_name = wiz_io.prompt_str(f"  Sub-profile name (optional, Enter to skip){default_hint}: ")
    name: Optional[str] = raw_name.strip() or existing_name or None

    # Standard constraints
    std_existing = existing.standard if existing is not None else None
    standard = _build_standard_constraints(std_existing)

    # Default: 2 if existing had a random-suit, 3 for partner-contingent,
    # 4 for opp-contingent, otherwise 1.
    default_choice = 1
    if existing is not None:
        if existing.random_suit_constraint is not None:
            default_choice = 2
        elif existing.partner_contingent_constraint is not None:
            default_choice = 3
        elif existing.opponents_contingent_suit_constraint is not None:
            default_choice = 4

    while True:
        print("\nExtra constraint for this sub-profile:")
        print("  1) None (Standard-only)")
        print("  2) Random Suit constraint")
        print("  3) Partner Contingent constraint (chosen or unchosen suit)")
        print("  4) Opponent Contingent-Suit constraint (chosen or unchosen suit)")
        print("  5) Help")

        choice = _input_int(
            "  Choose [1-5]",
            default=default_choice,
            minimum=1,
            maximum=5,
            show_range_suffix=False,
        )

        if choice == 5:
            print(get_menu_help("extra_constraint"))
            continue

        break

    random_constraint = None
    partner_constraint = None
    opponents_constraint = None

    if choice == 2:
        random_constraint = _build_random_suit_constraint(existing.random_suit_constraint if existing else None)
    elif choice == 3:
        partner_constraint = _build_partner_contingent_constraint(
            existing.partner_contingent_constraint if existing else None
        )
    elif choice == 4:
        opponents_constraint = _build_opponent_contingent_constraint(
            existing.opponents_contingent_suit_constraint if existing else None
        )

    # Weighting (seat-level weighting edits are handled separately.)
    weight_percent = existing.weight_percent if existing is not None else 0.0

    return SubProfile(
        standard=standard,
        name=name,
        random_suit_constraint=random_constraint,
        partner_contingent_constraint=partner_constraint,
        opponents_contingent_suit_constraint=opponents_constraint,
        weight_percent=weight_percent,
    )


def _assign_subprofile_weights_interactive(
    seat: str,
    subprofiles: List[SubProfile],
    existing: Optional[SeatProfile],
) -> List[SubProfile]:
    """
    Handle interactive weighting for the subprofiles of a given seat.

    Rules (per our design):

      • Legacy / old JSON where all weight_percent are 0.0:
          - Default equal weights 100/n (to 1 decimal) per sub-profile.
      • No negatives allowed.
      • If user edits weights:
          - We accept percentages that sum to 100 ± 2%.
          - If within ±2%, we normalise them to sum exactly 100.
          - Otherwise, we reject and re-prompt.
      • We never mutate frozen dataclasses in-place; instead we build
        new SubProfile instances via dataclasses.replace.
    """
    if len(subprofiles) <= 1:
        # Single sub-profile: treat as 100% and return.
        return [
            replace(subprofiles[0], weight_percent=100.0),
        ]

    # Derive existing weights from the SeatProfile if available.
    existing_weights: List[float] = []
    if existing is not None:
        for sub in existing.subprofiles:
            existing_weights.append(sub.weight_percent)

    # Detect "legacy" case: all zeros
    all_zero = all(w == 0.0 for w in existing_weights) if existing_weights else True

    if all_zero:
        equal_weight = round(100.0 / len(subprofiles), 1)
        default_weights = [equal_weight for _ in subprofiles]
    else:
        # Use existing (non-zero) weights as defaults, but ensure we have the right length.
        default_weights = [(existing_weights[i] if i < len(existing_weights) else 0.0) for i in range(len(subprofiles))]

    print(f"\nSub-profile weighting for seat {seat}:")
    for idx, w in enumerate(default_weights, start=1):
        suffix = " (default)" if all_zero else ""
        print(f"  {sub_label(idx, subprofiles[idx - 1])}: {w:.1f}% of deals{suffix}")

    # Menu: let user choose how to handle weights
    print("\n  0) Exit (keep weights as shown)")
    print("  1) Use current weights")
    print("  2) Use even weights")
    print("  3) Manually define weights")
    choice = prompt_int("Choice", default=0, minimum=0, maximum=3)

    if choice in (0, 1):
        # Keep current weights; normalise them to sum exactly 100 in case of rounding.
        total_default = sum(default_weights)
        if total_default <= 0:
            # Safeguard: if for some reason the defaults sum to 0, fall back to equal.
            equal_weight = round(100.0 / len(subprofiles), 1)
            default_weights = [equal_weight for _ in subprofiles]
            total_default = sum(default_weights)

        factor = 100.0 / total_default
        normalised = [round(w * factor, 1) for w in default_weights]
        return [replace(sub, weight_percent=normalised[i]) for i, sub in enumerate(subprofiles)]

    if choice == 2:
        # Even weights across all subprofiles
        n = len(subprofiles)
        equal_weight = round(100.0 / n, 1)
        even_weights = [equal_weight] * n
        # Adjust last weight so they sum to exactly 100
        even_weights[-1] = round(100.0 - sum(even_weights[:-1]), 1)
        print("\n  Even weights applied:")
        for idx, w in enumerate(even_weights, start=1):
            print(f"    {sub_label(idx, subprofiles[idx - 1])}: {w:.1f}%")
        return [replace(sub, weight_percent=even_weights[i]) for i, sub in enumerate(subprofiles)]

    # choice == 3: manually define weights.
    # Prompt for each weight, enforce no negatives, require total within ±2 of 100.
    while True:
        edited_weights: List[float] = []
        for i, sub in enumerate(subprofiles, start=1):
            default = default_weights[i - 1]
            prompt = f"  Weight for {sub_label(i, sub)} as % of deals (0–100, at most one decimal)"
            w = _input_float_with_default(
                prompt,
                default=default,
                min_value=0.0,
                max_value=100.0,
                decimal_places=1,
            )
            edited_weights.append(w)

        total = sum(edited_weights)
        if total <= 0.0:
            print("Total weight must be > 0. Please re-enter.")
            continue

        if abs(total - 100.0) > 2.0:
            print(f"Total weight {total:.1f}% is too far from 100% (must be within ±2% of 100). Please re-enter.")
            continue

        # Within ±2%: normalise
        factor = 100.0 / total
        normalised = [round(w * factor, 1) for w in edited_weights]

        return [replace(sub, weight_percent=normalised[i]) for i, sub in enumerate(subprofiles)]


def _valid_role_options_for_seat(
    seat: str,
    role_mode: str,
    pair_seats: tuple[str, str],
) -> list[str]:
    """
    Return the valid ew/ns_role_usage options for a seat given the role mode.

    Rules:
      - "no_driver":     only "any" (no driver/follower distinction)
      - "random_driver": all three (either seat could drive)
      - "<X>_drives":    driver seat gets any/driver_only,
                         follower seat gets any/follower_only
    """
    # Determine which seat is the driver for fixed-driver modes
    driver_map = {
        f"{pair_seats[0].lower()}_drives": pair_seats[0],
        f"{pair_seats[1].lower()}_drives": pair_seats[1],
    }

    if role_mode == "no_driver":
        # Index matching but no driver/follower — only "any" makes sense
        return ["any"]
    if role_mode == "random_driver":
        # Either seat could be driver or follower
        return ["any", "driver_only", "follower_only"]

    # Fixed driver mode (e.g. "north_drives", "east_drives")
    driver_seat = driver_map.get(role_mode)
    if driver_seat == seat:
        return ["any", "driver_only"]
    else:
        return ["any", "follower_only"]


def _assign_role_usage_for_subprofile(
    seat: str,
    sub: SubProfile,
    sub_idx: int,
    existing_sub: Optional[SubProfile],
    *,
    role_mode: str = "no_driver_no_index",
) -> SubProfile:
    """
    Prompt for role usage (driver/follower/any) for a single subprofile.

    For N/S seats: prompts for ns_role_usage.
    For E/W seats: prompts for ew_role_usage.

    The available options are restricted based on the role mode:
      - "no_driver":     auto-assigns "any" (no prompt)
      - "random_driver": offers any/driver_only/follower_only
      - "<X>_drives":    driver seat gets any/driver_only,
                         follower seat gets any/follower_only
    """
    if seat in ("N", "S"):
        pair_seats = ("N", "S")
        valid_options = _valid_role_options_for_seat(seat, role_mode, pair_seats)

        default_usage = existing_sub.ns_role_usage if existing_sub is not None else "any"
        # Clamp default to valid options (in case profile had an invalid tag)
        if default_usage not in valid_options:
            default_usage = "any"
        label = sub_label(sub_idx, sub)

        # If only "any" is valid, auto-assign without prompting
        if valid_options == ["any"]:
            return replace(sub, ns_role_usage="any")

        if not _yes_no_help(
            f"Edit NS driver/follower role for {label}?",
            "yn_edit_roles",
            default=False,
        ):
            return replace(sub, ns_role_usage=default_usage)

        options_str = "/".join(valid_options)
        prompt = f"  NS role usage for {label} ({options_str})"
        valid_set = set(valid_options)
        while True:
            raw = _input_with_default(prompt + f" [{default_usage}]: ", default_usage)
            value = raw.strip().lower()
            if value in valid_set:
                break
            print(f"Please enter one of: {options_str}")
        return replace(sub, ns_role_usage=value)

    if seat in ("E", "W"):
        pair_seats = ("E", "W")
        valid_options = _valid_role_options_for_seat(seat, role_mode, pair_seats)

        default_usage = existing_sub.ew_role_usage if existing_sub is not None else "any"
        # Clamp default to valid options (in case profile had an invalid tag)
        if default_usage not in valid_options:
            default_usage = "any"
        label = sub_label(sub_idx, sub)

        # If only "any" is valid, auto-assign without prompting
        if valid_options == ["any"]:
            return replace(sub, ew_role_usage="any")

        if not _yes_no_help(
            f"Edit EW driver/follower role for {label}?",
            "yn_edit_ew_roles",
            default=False,
        ):
            return replace(sub, ew_role_usage=default_usage)

        options_str = "/".join(valid_options)
        prompt = f"  EW role usage for {label} ({options_str})"
        valid_set = set(valid_options)
        while True:
            raw = _input_with_default(prompt + f" [{default_usage}]: ", default_usage)
            value = raw.strip().lower()
            if value in valid_set:
                break
            print(f"Please enter one of: {options_str}")
        return replace(sub, ew_role_usage=value)

    # Seats other than N/S/E/W — no role prompt
    return sub


def _build_seat_profile(
    seat: str,
    existing: Optional[SeatProfile] = None,
    current_exclusions: Optional[List[SubprofileExclusionData]] = None,
    *,
    ns_role_mode: str = "no_driver_no_index",
    ew_role_mode: str = "no_driver_no_index",
) -> tuple[SeatProfile, List[SubprofileExclusionData]]:
    """
    Build a SeatProfile interactively, including per-subprofile role and exclusion editing.

    Parameters:
        seat:               The seat letter (N/E/S/W).
        existing:           Existing SeatProfile to edit, or None for new.
        current_exclusions: Full list of all exclusions (all seats). This seat's
                            exclusions will be updated in-place for each subprofile.
        ns_role_mode:       Profile-level NS role mode. Role prompts are only shown
                            when a driver is configured (not "no_driver_no_index").
        ew_role_mode:       Profile-level EW role mode. Same logic as ns_role_mode.

    Returns:
        A tuple of (SeatProfile, updated_exclusions_list).
    """
    print(f"\n--- Seat {seat} ---")

    # Work with a mutable copy of the exclusions list
    all_exclusions = list(current_exclusions) if current_exclusions else []

    # Determine how many sub-profiles for this seat.
    default_subprofiles = 1 if existing is None else len(existing.subprofiles)
    prompt = f"How many sub-profiles for seat {seat}?"
    num_sub = _input_int(
        prompt,
        minimum=1,
        maximum=6,
        default=default_subprofiles,
    )

    subprofiles: List[SubProfile] = []
    # Collect exclusions for this seat, rebuilding as we go
    other_excls = [e for e in all_exclusions if e.seat != seat]
    this_seat_excls: List[SubprofileExclusionData] = []

    for idx in range(1, num_sub + 1):
        existing_sub = None
        if existing is not None and idx - 1 < len(existing.subprofiles):
            existing_sub = existing.subprofiles[idx - 1]
        # Show name if re-editing an existing named sub-profile.
        header = sub_label(idx, existing_sub) if existing_sub else f"Sub-profile {idx}"
        print(f"\n{header} for seat {seat}:\n")

        # Existing exclusions for this subprofile
        sub_excls = [e for e in all_exclusions if e.seat == seat and e.subprofile_index == idx]

        # When editing an existing sub-profile, let user skip to keep it as-is.
        # Skipping preserves constraints, role usage, AND exclusions unchanged.
        skipped = False
        if existing_sub is not None:
            if not _yes_no(f"Edit {header}?", default=True):
                subprofiles.append(existing_sub)
                this_seat_excls.extend(sub_excls)
                skipped = True

        if not skipped:
            sub = _build_subprofile(seat, existing_sub)
            subprofiles.append(sub)

            # --- Per-subprofile role assignment (right after constraints) ---
            # Only prompt for roles when a driver is configured for this pair.
            # "no_driver_no_index" means roles are irrelevant — skip entirely.
            current_sub = subprofiles[-1]
            ns_has_driver = seat in ("N", "S") and ns_role_mode != "no_driver_no_index"
            ew_has_driver = seat in ("E", "W") and ew_role_mode != "no_driver_no_index"

            if ns_has_driver or ew_has_driver:
                if num_sub > 1:
                    active_role_mode = ns_role_mode if ns_has_driver else ew_role_mode
                    current_sub = _assign_role_usage_for_subprofile(
                        seat,
                        current_sub,
                        idx,
                        existing_sub,
                        role_mode=active_role_mode,
                    )
                    subprofiles[-1] = current_sub
                else:
                    # Single subprofile: auto-assign "any" (preserve existing if editing)
                    if ns_has_driver:
                        default_role = existing_sub.ns_role_usage if existing_sub is not None else "any"
                        subprofiles[-1] = replace(current_sub, ns_role_usage=default_role)
                    elif ew_has_driver:
                        default_role = existing_sub.ew_role_usage if existing_sub is not None else "any"
                        subprofiles[-1] = replace(current_sub, ew_role_usage=default_role)

            # --- Per-subprofile exclusion editing (right after role) ---
            # Build a temporary SeatProfile so the display helpers work
            temp_sp = SeatProfile(seat=seat, subprofiles=list(subprofiles))
            updated_sub_excls = _edit_exclusions_for_subprofile(
                seat=seat,
                sub_idx=idx,
                sp=temp_sp,
                this_sub_excls=list(sub_excls),
            )
            this_seat_excls.extend(updated_sub_excls)

    # Handle weighting (returns a new list). Weights must sum to 100%
    # across all subprofiles, so this stays as a post-loop step.
    subprofiles = _assign_subprofile_weights_interactive(
        seat,
        subprofiles,
        existing,
    )

    seat_profile = SeatProfile(seat=seat, subprofiles=subprofiles)
    return seat_profile, other_excls + this_seat_excls


def _autosave_profile_draft(profile: HandProfile, original_path: Path) -> None:
    """
    Best-effort autosave of an in-progress profile edit.

    Draft rules (centralized in profile_store):
      - Writes sibling '<stem>_TEST.json'
      - JSON metadata profile_name ends with ' TEST'
      - Does NOT mutate the in-memory HandProfile
    """
    try:
        from . import profile_store

        profile_store.autosave_profile_draft(profile, canonical_path=original_path)
    except (ImportError, OSError, TypeError, ValueError):
        # Never let autosave kill the wizard
        return


def _build_profile(
    existing: Optional[HandProfile] = None,
    original_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Core interactive flow to build (or rebuild) a HandProfile.

    Used by:
      • create_profile_interactive()   (existing is None)
      • edit_constraints_interactive() (existing is a HandProfile)

    NEW BEHAVIOUR:
      - For brand-new profiles (existing is None):
          * Ask ONLY for metadata (name, tag, dealer, etc.).
          * Automatically attach standard constraints for all four seats:
              - 1 sub-profile per seat
              - Standard 'all-open' ranges
              - No non-standard constraints or exclusions
              - N/S ns_role_usage = 'no_driver_no_index'
              - E/W ew_role_usage = 'no_driver_no_index'
          * No constraints wizard prompts.
      - For edits (existing is not None):
          * Preserve the full constraints wizard behaviour, including
            seat-by-seat editing, subprofile weights, NS/EW role usage, and
            autosave of _TEST.json drafts.
    """

    # Route interaction helpers through profile_wizard when tests monkeypatch there.
    input_with_default = _pw_attr("_input_with_default", _input_with_default)
    input_choice = _pw_attr("_input_choice", _input_choice)
    seat_builder = _pw_attr("_build_seat_profile", _build_seat_profile)

    # Rotation is metadata; constraints edit must preserve existing value (default True).
    rotate_flag = existing.rotate_deals_by_default if existing is not None else True

    # ----- Metadata (and rotation flag) -----
    if existing is not None:
        # EDIT FLOW: reuse metadata from existing profile
        profile_name = existing.profile_name
        description = existing.description
        tag = existing.tag
        dealer = existing.dealer
        hand_dealing_order = list(existing.hand_dealing_order)
        author = existing.author
        version = existing.version

    else:
        # CREATE FLOW: metadata-only UI
        profile_name = input_with_default("Profile name: ", "New profile")
        description = input_with_default("Description: ", "")

        tag = input_choice(
            "Tag [Opener/Overcaller]: ",
            ["Opener", "Overcaller"],
            "Opener",
        )

        dealer = input_choice(
            "Dealer seat [N/E/S/W]: ",
            ["N", "E", "S", "W"],
            "N",
        )

        # Dealing order is auto-computed at runtime by v2 builder
        # (_compute_dealing_order).  Store clockwise from dealer as default.
        hand_dealing_order = _default_dealing_order(dealer)

        author = input_with_default("Author: ", "")
        version = input_with_default("Version: ", "0.1")

        # ----- NEW: auto-build standard constraints for all seats -----
        seat_profiles: Dict[str, SeatProfile] = {}
        for seat in hand_dealing_order:
            seat_profiles[seat] = _make_default_standard_seat_profile(seat)

        # Brand-new profile: no exclusions yet
        subprofile_exclusions: List[SubprofileExclusionData] = []

        # Default ns/ew_role_mode for new profiles
        ns_role_mode = "no_driver_no_index"
        ew_role_mode = "no_driver_no_index"

        # We do NOT autosave draft files for brand-new profiles here; the
        # profile will be validated and saved via profile_cli.
        return {
            "profile_name": profile_name,
            "description": description,
            "dealer": dealer,
            "hand_dealing_order": hand_dealing_order,
            "tag": tag,
            "seat_profiles": seat_profiles,
            "author": author,
            "version": version,
            "rotate_deals_by_default": rotate_flag,
            "ns_role_mode": ns_role_mode,
            "ew_role_mode": ew_role_mode,
            "subprofile_exclusions": subprofile_exclusions,
        }

    # ------------------------------------------------------------------
    # EDIT FLOW (existing is not None): full constraints wizard
    # ------------------------------------------------------------------

    seat_profiles: Dict[str, SeatProfile] = {}  # type: ignore[no-redef]
    subprofile_exclusions: List[SubprofileExclusionData] = list(  # type: ignore[no-redef]
        existing.subprofile_exclusions or []
    )

    for seat in hand_dealing_order:
        print(f"\n--- Editing constraints for seat {seat} ---")

        existing_seat_profile: Optional[SeatProfile] = existing.seat_profiles.get(seat)

        # y = edit this seat, n = skip (keep existing), e = save & exit loop
        choice = _prompt_yne(
            f"Edit seat {seat} constraints, or save and exit?",
            default="y",
        )
        if choice == "e":
            # Save and exit: keep existing profiles for this and all remaining seats
            for remaining_seat in hand_dealing_order[hand_dealing_order.index(seat) :]:
                ep = existing.seat_profiles.get(remaining_seat)
                if ep is not None:
                    seat_profiles[remaining_seat] = ep
            break
        if choice == "n":
            if existing_seat_profile is not None:
                seat_profiles[seat] = existing_seat_profile
            continue

        # EDIT FLOW: call _build_seat_profile with (seat, existing, exclusions).
        # Role prompts and exclusion editing now happen per-subprofile inside
        # _build_seat_profile, so no separate exclusion call is needed here.
        result = seat_builder(
            seat,
            existing_seat_profile,
            subprofile_exclusions,
            ns_role_mode=existing.ns_role_mode,
            ew_role_mode=existing.ew_role_mode,
        )
        # Handle both tuple return (new) and plain SeatProfile (legacy monkeypatch)
        if isinstance(result, tuple):
            new_seat_profile, subprofile_exclusions = result
        else:
            new_seat_profile = result
        seat_profiles[seat] = new_seat_profile

        # --- Autosave draft after each seat (best-effort) ---
        if original_path is not None:
            try:
                ns_role_mode = existing.ns_role_mode
                ew_role_mode = existing.ew_role_mode
                snapshot = HandProfile(
                    profile_name=profile_name,
                    description=description,
                    dealer=dealer,
                    hand_dealing_order=list(hand_dealing_order),
                    tag=tag,
                    seat_profiles=seat_profiles,
                    author=author,
                    version=version,
                    rotate_deals_by_default=rotate_flag,
                    ns_role_mode=ns_role_mode,
                    ew_role_mode=ew_role_mode,
                    subprofile_exclusions=list(subprofile_exclusions),
                    sort_order=existing.sort_order,
                )
                _autosave_profile_draft(snapshot, original_path)
            except Exception as exc:  # pragma: no cover – autosave is best-effort
                print(f"WARNING: Autosave failed after seat {seat}: {exc}")

    # ----- Final kwargs dict for HandProfile (edit flow) -----
    ns_role_mode = existing.ns_role_mode
    ew_role_mode = existing.ew_role_mode

    return {
        "profile_name": profile_name,
        "description": description,
        "dealer": dealer,
        "hand_dealing_order": hand_dealing_order,
        "tag": tag,
        "seat_profiles": seat_profiles,
        "author": author,
        "version": version,
        "rotate_deals_by_default": rotate_flag,
        "ns_role_mode": ns_role_mode,
        "ew_role_mode": ew_role_mode,
        "subprofile_exclusions": list(subprofile_exclusions),
        "sort_order": existing.sort_order,
    }


def edit_constraints_interactive(
    existing: HandProfile,
    profile_path: Optional[Path] = None,
) -> HandProfile:
    """
    Top-level helper for editing only the constraints of an existing profile.

    Metadata (name, description, tag, author, version) are preserved from
    the existing profile. Dealer and dealing order are also preserved.

    If profile_path is provided, the wizard will autosave a draft
    '<original_name>_TEST.json' after each seat is edited.
    """
    clear_screen()
    print("=== Edit Constraints for Profile ===")
    print(f"Profile: {existing.profile_name}")
    print(f"Dealer : {existing.dealer}")
    print(f"Order  : {list(existing.hand_dealing_order)}\n")

    kwargs = _build_profile(existing=existing, original_path=profile_path)
    profile = HandProfile(**kwargs)
    validate_profile(profile)
    return profile
