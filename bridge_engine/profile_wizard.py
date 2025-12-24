"""Wizard entrypoints and stable monkeypatch seams.
This module is intentionally a *façade* over the wizard implementation modules.
Tests and callers should import from `bridge_engine.profile_wizard` and may
monkeypatch helpers like `_input_int` or symbols like `HandProfile`.
Design goals:
- Keep historical public attributes stable (tests monkeypatch these).
- Delegate implementation to wizard_* modules without creating circular imports.
"""

from __future__ import annotations
from dataclasses import replace
from typing import Optional

# ---- Model + validation seams (tests monkeypatch these) ----------------------
# HandProfile/validate_profile are expected to be available here so tests can do:
#   monkeypatch.setattr(profile_wizard, "HandProfile", DummyHandProfile)
# and so the wizard uses the patched symbol.

from .hand_profile_model import HandProfile
from .hand_profile import HandProfile, validate_profile  # type: ignore

# ---- I/O seams (tests monkeypatch these) ------------------------------------

# These are imported from wizard_io but re-exported here so tests can patch
# `bridge_engine.profile_wizard._input_int` and wizard code will see it.
from .wizard_io import (  # type: ignore
    clear_screen,
    _input_with_default,
    _input_int,
    _input_bool,
    _input_choice,
    _yes_no,
)

# ---- Wizard flow / builders -------------------------------------------------

# Entry points expected by CLI:
from .wizard_flow import (  # type: ignore
    create_profile_interactive,
    edit_constraints_interactive,
)

# Internal helpers used by unit tests:
from .wizard_flow import (  # type: ignore
    _build_suit_range_for_prompt,
    _build_standard_constraints,
    _build_seat_profile,
    _build_profile,
)

from . import wizard_flow

# Some repos/tests import additional helpers; re-exporting is harmless.
try:
    from .wizard_flow import (  # type: ignore
        _build_card_range_for_prompt,
        _build_hcp_range_for_prompt,
        _build_ace_range_for_prompt,
        _build_king_range_for_prompt,
        _build_queen_range_for_prompt,
        _build_jack_range_for_prompt,
    )
except Exception:
    # Not all versions have these helpers; ignore if absent.
    pass

def create_profile_interactive() -> HandProfile:
    print("\n=== Create New Profile ===\n")
    kwargs = wizard_flow._build_profile(existing=None)
    profile = HandProfile(**kwargs)
    validate_profile(profile)
    # existing save / filename logic can use `profile` as before
    return profile

def create_profile_from_existing_constraints(existing: HandProfile) -> HandProfile:
    """
    Create a new profile that reuses all constraints from `existing`
    (seat_profiles + subprofile_exclusions) but lets the user enter new
    metadata fields (name, description, tag, dealer, dealing order,
    author, version, rotate_deals_by_default).

    This is intended for “new standard profile” flows built from a
    base template; constraint tweaks are done later via
    edit_constraints_interactive().
    """
    clear_screen()
    print("=== Create New Profile (from template) ===")
    print()
    print(f"Starting from template: {existing.profile_name}")
    print()

    # Metadata-only – constraints come entirely from `existing`.
    kwargs = _build_profile(
        existing=existing,
        original_path=None,
        constraints_mode="metadata_only",
    )

    profile = HandProfile(**kwargs)
    validate_profile(profile)
    return profile
    
def edit_constraints_interactive(existing: HandProfile) -> HandProfile:
    print("\n=== Edit Constraints for Profile ===")
    print(f"Profile: {existing.profile_name}")
    print(f"Dealer : {existing.dealer}")
    print(f"Order  : {list(existing.hand_dealing_order)}\n")

    kwargs = wizard_flow._build_profile(existing=existing)
    profile = HandProfile(**kwargs)
    validate_profile(profile)
    # any save logic here should use `profile`
    return profile

__all__ = [
    # model/validation
    "HandProfile",
    "validate_profile",
    # I/O seams
    "clear_screen",
    "_input_with_default",
    "_input_int",
    "_input_bool",
    "_input_choice",
    "_yes_no",
    # entrypoints
    "create_profile_interactive",
    "edit_constraints_interactive",
    # tested builders
    "_build_suit_range_for_prompt",
    "_build_standard_constraints",
    "_build_seat_profile",
]
