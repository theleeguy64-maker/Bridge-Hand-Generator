"""
Interactive wizard helpers for building and editing HandProfile objects.

This module centralises the interactive, prompt-driven construction of
profiles so that both the CLI and tests can rely on a single behaviour.
"""

# TEST CONTRACT — profile_wizard.py
#
# The following symbols are intentionally monkeypatched by tests and must remain
# defined at module scope. Do not rename or remove without updating tests.
# 
# Prompt wrappers (tests control interactive behavior):
#   - _input_with_default(prompt: str, default: str) -> str
#   - _input_int(prompt, default, minimum, maximum, show_range_suffix=True) -> int
#   - _yes_no(prompt: str, default: bool = True) -> bool
#   - clear_screen()
# 
# Builder / flow helpers patched by tests:
#   - _build_seat_profile(seat: str)
#   - _build_profile(existing: Optional[HandProfile] = None)
#   - create_profile_interactive()
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

# file: bridge_engine/profile_wizard.py

from __future__ import annotations

import sys

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Iterable

from . import cli_io
from . import profile_store
from .menu_help import get_menu_help
from .wizard_io import _input_choice
from .wizard_constants import SUITS
from . import wizard_io as wiz_io
from .hand_profile_validate import validate_profile as _validate_profile_fallback

from .cli_prompts import (
    prompt_choice,
    prompt_int,
    prompt_text,
    prompt_yes_no as _prompt_yes_no,
)

from .hand_profile_model import (
    HandProfile,
    SeatProfile,
    SubProfile,
    SubprofileExclusionData,
    StandardSuitConstraints,
    SuitRange,
    OpponentContingentSuitData,
    _default_dealing_order,
)


def _validate_profile(profile) -> None:
    return _pw_attr("validate_profile", _validate_profile_fallback)(profile)

# NOTE: pytest monkeypatches input helpers on bridge_engine.profile_wizard.
# After splitting the wizard into modules, we route interactive I/O through
# that module when available (falling back to wizard_io). This preserves the
# stable monkeypatch seam expected by tests.
def _pw_attr(name: str, fallback):
    """
    Late attribute lookup on the already-imported profile_wizard module.
    This preserves monkeypatch seams even if imports happen in different order.
    """    
    pw = sys.modules.get("bridge_engine.profile_wizard")
    if pw is None:    
        try:
            from . import profile_wizard as pw  # local import avoids cycles at import time
        except Exception:
            return fallback
            
    return getattr(pw, name, fallback)
        
def _yes_no(prompt: str, default: bool = True) -> bool:
    return _pw_attr("_yes_no", wiz_io._yes_no)(prompt, default=default)

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
            f"{prompt} ({options_str})"
            + (f" [{default}]" if default is not None else "")
            + ": ",
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
    PartnerContingentData,
    RandomSuitConstraintData,
    SeatProfile,
    StandardSuitConstraints,
    SubProfile,
    SubprofileExclusionClause,
    SubprofileExclusionData,
    SuitRange,
    OpponentContingentSuitData,
    validate_profile,
)


# ---------------------------------------------------------------------------
# Sub-profile exclusions (F2) — wizard helpers
# ---------------------------------------------------------------------------

def _parse_shapes_csv(raw: str) -> list[str]:
    shapes: list[str] = []
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
    # If kind not provided, prompt for it (backward compat)
    if not kind:
        kind = _input_choice(
            "Exclusion type (shapes=exact 4-digit patterns, rule=ANY/MAJOR/MINOR clauses)",
            options=["shapes", "rule"],
            default="shapes",
        )

    if kind == "shapes":
        raw = _input_with_default(
            "Enter excluded shapes as comma-separated 4-digit S/H/D/C patterns "
            "that sum to 13 (e.g. 4333,4432): ",
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
    clauses: list[SubprofileExclusionClause] = []
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
        clauses.append(
            SubprofileExclusionClause(group=group, length_eq=length_eq, count=count)
        )

        if idx < max_clauses and not _yes_no("Add a second clause? ", default=False):
            break

    return SubprofileExclusionData(
        seat=seat,
        subprofile_index=subprofile_index,
        excluded_shapes=None,
        clauses=clauses,
    )
    
# Near other small helpers in wizard_flow.py

def _build_exclusion_shapes(
    seat: Any,
    subprofile_index: Optional[int] = None,
) -> List[str]:
    """
    Build a list of shape strings for use in the exclusions wizard.

    This is deliberately duck-typed so tests (and future callers) can
    use simple dummy objects instead of the real SeatProfile/SubProfile
    classes.

    Rules (best-effort, no hard schema assumptions):

    - `seat` is expected to expose `.subprofiles` (iterable).
    - If `subprofile_index` is not None and in range, we only inspect
      that subprofile; otherwise we inspect all subprofiles on the seat.
    - For each selected subprofile we look, in order, for:

        * a string attribute `shape_string` or `shape`, e.g. "5-3-3-2"
        * or a 4-tuple / 4-list attribute named one of
          ("shape", "shape_tuple", "suit_lengths", "suit_counts")

      and normalise 4-int sequences into "x-y-z-w" strings.

    - We deduplicate while preserving first-seen order.
    - If nothing shape-like can be found, we return an empty list.
    """

    # --- internal helper -------------------------------------------------
    def _shape_from_sub(sub: Any) -> Optional[str]:
        if sub is None:
            return None

        # 1) Direct string attributes.
        for attr in ("shape_string", "shape"):
            val = getattr(sub, attr, None)
            if isinstance(val, str) and val.strip():
                return val.strip()

        # 2) 4-card-count sequence attributes.
        for attr in ("shape", "shape_tuple", "suit_lengths", "suit_counts"):
            val = getattr(sub, attr, None)
            if isinstance(val, (list, tuple)) and len(val) == 4 and all(
                isinstance(n, int) for n in val
            ):
                return "-".join(str(int(n)) for n in val)

        # If we can't recognise anything, skip this subprofile.
        return None

    # --- select which subprofiles we care about --------------------------
    subs = getattr(seat, "subprofiles", None)
    if not isinstance(subs, Iterable):
        return []

    # Normalise to a list so we can index safely.
    subs_list = list(subs)

    if subprofile_index is not None:
        try:
            selected_subs: Iterable[Any] = [subs_list[subprofile_index]]
        except IndexError:
            selected_subs = []
    else:
        selected_subs = subs_list

    # --- build unique shape list -----------------------------------------
    seen: set[str] = set()
    shapes: List[str] = []

    for sub in selected_subs:
        shape_str = _shape_from_sub(sub)
        if not shape_str:
            continue
        if shape_str in seen:
            continue
        seen.add(shape_str)
        shapes.append(shape_str)

    return shapes


def _edit_subprofile_exclusions_for_seat(
    *,
    existing: Optional[HandProfile],
    seat: str,
    seat_profiles: Dict[str, SeatProfile],
    current_all: List[SubprofileExclusionData],
) -> List[SubprofileExclusionData]:
    """
    Edit exclusions for ONE seat, returning the updated full exclusions list.

    Storage model remains global list; this helper just provides a seat-local UI.
    """
    # Partition: this seat vs other seats
    this_seat = [e for e in current_all if e.seat == seat]
    other = [e for e in current_all if e.seat != seat]

    sp = seat_profiles.get(seat)
    if sp is None or not getattr(sp, "subprofiles", None):
        print(f"(No sub-profiles for seat {seat}; exclusions not applicable.)")
        return current_all

    # If no existing for this seat, optionally skip
    default_edit = True if this_seat else False
    if not _yes_no(
        f"Add/edit sub-profile exclusions for seat {seat}? ",
        default=default_edit,
    ):
        return current_all

    # Show existing exclusions for this seat (if any)
    if this_seat:
        print(f"\nExisting exclusions for seat {seat}:")
        for i, exc in enumerate(this_seat, start=1):
            kind = "shapes" if exc.excluded_shapes else "rule"
            print(f"  {i}) sub-profile {exc.subprofile_index} ({kind})")

        # Simple edit loop: remove entries
        while True:
            if not _yes_no("Remove any exclusion for this seat? ", default=False):
                break
            n = _input_int(
                f"Which exclusion # to remove (1–{len(this_seat)})",
                default=1,
                minimum=1,
                maximum=len(this_seat),
            )
            this_seat.pop(n - 1)

    # Ask sub-profile index once before the menu loop
    sub_idx = _input_int(
        f"Sub-profile index for seat {seat} (1–{len(sp.subprofiles)})",
        default=1,
        minimum=1,
        maximum=len(sp.subprofiles),
    )

    # Numbered menu loop for adding exclusions
    while True:
        print(f"\nExclusion menu for seat {seat}, sub-profile {sub_idx}:")
        print("  0) Exit")
        print("  1) Add shapes exclusion")
        print("  2) Add rule exclusion")
        print("  3) Help")

        choice = _input_int("Choice", default=0, minimum=0, maximum=3)

        if choice == 0:
            break
        elif choice == 1:
            exc = _build_exclusion_rule(seat=seat, subprofile_index=sub_idx, kind="shapes")
            this_seat.append(exc)
        elif choice == 2:
            exc = _build_exclusion_rule(seat=seat, subprofile_index=sub_idx, kind="rule")
            this_seat.append(exc)
        elif choice == 3:
            print(get_menu_help("exclusions"))

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

    sub_kwargs: dict[str, object] = {}
    
    sub = SubProfile(
        standard=std,
        **sub_kwargs,
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
    # Show exactly the prompt we were given – no extra duplicated text.
    raw = input(prompt).strip().upper()

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

    # For now we only care about existing when provided; otherwise defaults
    existing_spades = getattr(existing, "spades", None)
    existing_hearts = getattr(existing, "hearts", None)
    existing_diamonds = getattr(existing, "diamonds", None)
    existing_clubs = getattr(existing, "clubs", None)

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

def _prompt_standard_constraints(
    existing: Optional[StandardSuitConstraints],
) -> StandardSuitConstraints:
    """
    Wrapper used by the interactive sub-profile builder.
    """
    return _build_standard_constraints(existing)

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
    ).upper()
    if partner_seat not in ("N", "E", "S", "W"):
        print("Invalid seat; defaulting to N.")
        partner_seat = "N"

    # Extract existing suit range if editing an existing constraint.
    existing_suit_range = existing.suit_range if existing is not None else None

    suit_range = _prompt_suit_range("Partner suit", existing_suit_range)

    return PartnerContingentData(
        partner_seat=partner_seat,
        suit_range=suit_range,
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

    # Use the same SuitRange prompt helper used elsewhere in this wizard.
    # (This should exist because you saw: 'Define SuitRange for Clubs:' etc.)
    suit_range = _prompt_suit_range(
        "Suit",
        existing.suit_range if existing is not None else None,
    )

    return OpponentContingentSuitData(
        opponent_seat=opponent_seat,
        suit_range=suit_range,
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
        f"  Allowed suits (any order) "
        f"(e.g. SHC for Spades, Hearts, Clubs) "
        f"(default {default_allowed_str}): ",
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
        f"  Number of suits that must meet the random-suit criteria",
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
    pair_overrides = list(getattr(existing, "pair_overrides", [])) if existing else []

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

    # Standard constraints
    std_existing = existing.standard if existing is not None else None
    standard = _prompt_standard_constraints(std_existing)

    print("\nExtra constraint for this sub-profile:")
    print("  1) None (Standard-only)")
    print("  2) Random Suit constraint")
    print("  3) Partner Contingent constraint")
    print("  4) Opponent Contingent-Suit constraint")

    # Default: 2 if existing had a random-suit, 3 for partner-contingent,
    # 4 for opp-contingent, otherwise 1.
    default_choice = 1
    if existing is not None:
        if existing.random_suit_constraint is not None:
            default_choice = 2
        elif existing.partner_contingent_constraint is not None:
            default_choice = 3
        elif getattr(existing, "opponents_contingent_suit_constraint", None) is not None:
            default_choice = 4

    choice = _input_int(
        "  Choose [1-4]",
        default=default_choice,
        minimum=1,
        maximum=4,
        show_range_suffix=False,
    )

    random_constraint = None
    partner_constraint = None
    opponents_constraint = None

    if choice == 2:
        random_constraint = _build_random_suit_constraint(
            existing.random_suit_constraint if existing else None
        )
    elif choice == 3:
        partner_constraint = _build_partner_contingent_constraint(
            existing.partner_contingent_constraint if existing else None
        )
    elif choice == 4:
        opponents_constraint = _build_opponent_contingent_constraint(
            getattr(existing, "opponents_contingent_suit_constraint", None)
            if existing
            else None
        )

    # Weighting (seat-level weighting edits are handled separately.)
    weight_percent = existing.weight_percent if existing is not None else 0.0

    return SubProfile(
        standard=standard,
        random_suit_constraint=random_constraint,
        partner_contingent_constraint=partner_constraint,
        opponents_contingent_suit_constraint=opponents_constraint,
        weight_percent=weight_percent,
    )

def _build_subprofile_for_seat(
    seat: str,
    existing_sub: Optional[SubProfile] = None,
) -> SubProfile:
    """
    Wrapper used by tests and edit_constraints_interactive to build a subprofile.
    """
    return _build_subprofile(seat, existing_sub)

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
            existing_weights.append(getattr(sub, "weight_percent", 0.0))

    # Detect "legacy" case: all zeros
    all_zero = all(w == 0.0 for w in existing_weights) if existing_weights else True

    if all_zero:
        equal_weight = round(100.0 / len(subprofiles), 1)
        default_weights = [equal_weight for _ in subprofiles]
    else:
        # Use existing (non-zero) weights as defaults, but ensure we have the right length.
        default_weights = [
            (existing_weights[i] if i < len(existing_weights) else 0.0)
            for i in range(len(subprofiles))
        ]

    print(f"\nSub-profile weighting for seat {seat}:")
    for idx, w in enumerate(default_weights, start=1):
        suffix = " (default)" if all_zero else ""
        print(f"  Sub-profile {idx}: {w:.1f}% of deals{suffix}")

    if not _yes_no("Do you want to edit these weights?", default=False):
        # User kept defaults; normalise them to sum exactly 100 in case of rounding.
        total_default = sum(default_weights)
        if total_default <= 0:
            # Safeguard: if for some reason the defaults sum to 0, fall back to equal.
            equal_weight = round(100.0 / len(subprofiles), 1)
            default_weights = [equal_weight for _ in subprofiles]
            total_default = sum(default_weights)

        factor = 100.0 / total_default
        normalised = [round(w * factor, 1) for w in default_weights]
        return [
            replace(sub, weight_percent=normalised[i])
            for i, sub in enumerate(subprofiles)
        ]

    # If the user wants to edit, we prompt for each weight,
    # enforce no negatives, and require the total to be within ±2 of 100.
    while True:
        edited_weights: List[float] = []
        for i, sub in enumerate(subprofiles, start=1):
            default = default_weights[i - 1]
            prompt = (
                f"  Weight for sub-profile {i} as % of deals "
                f"(0–100, at most one decimal)"
            )
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
            print(
                f"Total weight {total:.1f}% is too far from 100% "
                "(must be within ±2% of 100). Please re-enter."
            )
            continue

        # Within ±2%: normalise
        factor = 100.0 / total
        normalised = [round(w * factor, 1) for w in edited_weights]

        return [
            replace(sub, weight_percent=normalised[i])
            for i, sub in enumerate(subprofiles)
        ]

def _build_seat_profile(
    seat: str,
    existing: Optional[SeatProfile] = None,
) -> SeatProfile:
    print(f"\n--- Seat {seat} ---")

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
    for idx in range(1, num_sub + 1):
        print(f"\nSub-profile {idx} for seat {seat}:\n")
        existing_sub = None
        if existing is not None and idx - 1 < len(existing.subprofiles):
            existing_sub = existing.subprofiles[idx - 1]
        sub = _build_subprofile_for_seat(seat, existing_sub)
        subprofiles.append(sub)

    # First, handle weighting (returns a new list).
    subprofiles = _assign_subprofile_weights_interactive(
        seat,
        subprofiles,
        existing,
    )

    # Then, for N/S seats, mark ns_role_usage on each subprofile.
    _assign_ns_role_usage_interactive(
        seat,
        subprofiles,
        existing,
    )

    return SeatProfile(seat=seat, subprofiles=subprofiles)
    
def _assign_ns_role_usage_interactive(
    seat: str,
    subprofiles: list[SubProfile],
    existing_seat_profile: Optional[SeatProfile],
) -> None:
    """
    Optional UI to tag N/S sub-profiles as:
      - 'any'           (default)
      - 'driver_only'
      - 'follower_only'

    Only applies to N/S. E/W are always treated as 'any' in NS driver logic.
    """
    # Only NS can be driver/follower in the current semantics.
    if seat not in ("N", "S"):
        return

    if not subprofiles:
        return

    # Start from existing values if we have them, else default to "any".
    existing_usage: list[str] = []
    if existing_seat_profile is not None:
        for sp in existing_seat_profile.subprofiles:
            existing_usage.append(getattr(sp, "ns_role_usage", "any"))

    n = len(subprofiles)
    if not existing_usage:
        defaults = ["any"] * n
    else:
        # Extend/truncate to match the new count.
        defaults = (existing_usage + ["any"] * n)[:n]

    print(f"\nNS role usage for seat {seat}:")
    for idx, role in enumerate(defaults, start=1):
        print(f"  Sub-profile {idx}: {role}")

    # Let the user opt in; default is 'no' so beginners aren't bothered.
    if not _yes_no(
        "Do you want to edit driver/follower roles for these sub-profiles? ",
        default=False,
    ):
        # Just write defaults back into the new objects.
        for sub, usage in zip(subprofiles, defaults):
            object.__setattr__(sub, "ns_role_usage", usage)
        return

    # User wants to edit them.
    valid_options = {"any", "driver_only", "follower_only"}

    for idx, default_usage in enumerate(defaults, start=1):
        prompt = (
            f"  NS role usage for sub-profile {idx} "
            "(any/driver_only/follower_only)"
        )
        while True:
            raw = _input_with_default(
                prompt + f" [{default_usage}]: ",
                default_usage,
            )
            value = raw.strip().lower()
            if value in valid_options:
                break
            print("Please enter one of: any, driver_only, follower_only")
        object.__setattr__(subprofiles[idx - 1], "ns_role_usage", value)


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
    except Exception:
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
          * No constraints wizard prompts.
      - For edits (existing is not None):
          * Preserve the full constraints wizard behaviour, including
            seat-by-seat editing, subprofile weights, NS role usage, and
            autosave of _TEST.json drafts.
    """

    # Route interaction helpers through profile_wizard when tests monkeypatch there.
    input_with_default = _pw_attr("_input_with_default", _input_with_default)
    input_choice = _pw_attr("_input_choice", _input_choice)
    yes_no = _pw_attr("_yes_no", _yes_no)
    seat_builder = _pw_attr("_build_seat_profile", _build_seat_profile)

    # Rotation is metadata; constraints edit must preserve existing value (default True).
    rotate_flag = getattr(existing, "rotate_deals_by_default", True)
    
    # ----- Metadata (and rotation flag) -----
    if existing is not None:
        # EDIT FLOW: reuse metadata from existing profile
        profile_name = existing.profile_name
        description = existing.description
        tag = existing.tag
        dealer = existing.dealer
        hand_dealing_order = list(existing.hand_dealing_order)
        author = getattr(existing, "author", "")
        version = getattr(existing, "version", "")

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

        # Default ns_role_mode for new profiles
        ns_role_mode = "no_driver_no_index"

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
            "subprofile_exclusions": subprofile_exclusions,
        }

    # ------------------------------------------------------------------
    # EDIT FLOW (existing is not None): full constraints wizard
    # ------------------------------------------------------------------
    seat_profiles: Dict[str, SeatProfile] = {}
    subprofile_exclusions: List[SubprofileExclusionData] = list(
        getattr(existing, "subprofile_exclusions", []) or []
    )

    for seat in hand_dealing_order:
        print(f"\n--- Editing constraints for seat {seat} ---")

        existing_seat_profile: Optional[SeatProfile] = existing.seat_profiles.get(seat)

        # In edit flow, tests fake _yes_no here to *skip* editing seats.
        if not yes_no(
            f"Do you want to edit constraints for seat {seat}?",
            default=True,
        ):
            if existing_seat_profile is not None:
                seat_profiles[seat] = existing_seat_profile
            continue

        # EDIT FLOW: call _build_seat_profile with (seat, existing)
        new_seat_profile = seat_builder(seat, existing_seat_profile)
        seat_profiles[seat] = new_seat_profile

        subprofile_exclusions = _edit_subprofile_exclusions_for_seat(
            existing=existing,
            seat=seat,
            seat_profiles=seat_profiles,
            current_all=subprofile_exclusions,
        )

        # --- Autosave draft after each seat (best-effort) ---
        if original_path is not None:
            try:
                ns_role_mode = getattr(
                    existing,
                    "ns_role_mode",
                    "no_driver_no_index",
                )
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
                    subprofile_exclusions=list(subprofile_exclusions),
                    sort_order=getattr(existing, "sort_order", None),
                )
                _autosave_profile_draft(snapshot, original_path)
            except Exception as exc:  # pragma: no cover – autosave is best-effort
                print(f"WARNING: Autosave failed after seat {seat}: {exc}")

    # ----- Final kwargs dict for HandProfile (edit flow) -----
    ns_role_mode = getattr(existing, "ns_role_mode", "no_driver_no_index")

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
        "subprofile_exclusions": list(subprofile_exclusions),
        "sort_order": getattr(existing, "sort_order", None),
    }
         
def create_profile_interactive() -> HandProfile:
    """
    Top-level helper for creating a new profile interactively.

    New behaviour:
      • Ask ONLY for profile metadata (name, tag, dealer, order, author, version,
        rotate flag).
      • Automatically attach standard "open" constraints to all four seats
        (N, E, S, W) – one sub-profile per seat, weight 100%, ns_role_usage="any".
      • NS role metadata defaults to "no_driver_no_index".
      • Users can later refine constraints via edit_constraints_interactive().
    """
    clear_screen()
    print("=== Create New Profile ===")
    print()

    # ---- Metadata prompts (same feel as before) ---------------------------
    profile_name = _input_with_default("Profile name: ", "New profile")
    description = _input_with_default("Description: ", "")

    tag = _input_choice(
        "Tag [Opener/Overcaller]: ",
        ["Opener", "Overcaller"],
        "Opener",
    )

    dealer = _input_choice(
        "Dealer seat [N/E/S/W]: ",
        ["N", "E", "S", "W"],
        "N",
    )

    # New default NS role mode for fresh profiles.
    ns_role_mode = "no_driver_no_index"

    # Dealing order is auto-computed at runtime by v2 builder
    # (_compute_dealing_order).  Store clockwise from dealer as default.
    hand_dealing_order = _default_dealing_order(dealer)

    author = _input_with_default("Author: ", "")
    version = _input_with_default("Version: ", "0.1")

    # ---- Standard constraints for all seats -------------------------------
    seat_profiles: Dict[str, SeatProfile] = {}

    for seat in ("N", "E", "S", "W"):
        # Completely open "standard" ranges:
        std = StandardSuitConstraints()
        sub = SubProfile(
            standard=std,
            random_suit_constraint=None,
            partner_contingent_constraint=None,
            opponents_contingent_suit_constraint=None,
            weight_percent=100.0,
            ns_role_usage="any",
        )
        seat_profiles[seat] = SeatProfile(seat=seat, subprofiles=[sub])

    # No exclusions on a fresh standard profile
    subprofile_exclusions: List[SubprofileExclusionData] = []

    # Build the HandProfile via the same indirection tests use
    hp_cls = _pw_attr("HandProfile", HandProfile)
    profile = hp_cls(
        profile_name=profile_name,
        description=description,
        dealer=dealer,
        hand_dealing_order=hand_dealing_order,
        tag=tag,
        seat_profiles=seat_profiles,
        author=author,
        version=version,
        rotate_deals_by_default=True,
        ns_role_mode=ns_role_mode,
        subprofile_exclusions=subprofile_exclusions,
    )

    # Run normal validation so new profiles behave like edited/loaded ones.
    _validate_profile(profile)
    return profile

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