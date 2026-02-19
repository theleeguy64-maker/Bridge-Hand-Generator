"""Wizard entrypoints and stable monkeypatch seams.
This module is intentionally a *façade* over the wizard implementation modules.
Tests and callers should import from `bridge_engine.profile_wizard` and may
monkeypatch helpers like `_input_int` or symbols like `HandProfile`.
Design goals:
- Keep historical public attributes stable (tests monkeypatch these).
- Delegate implementation to wizard_* modules without creating circular imports.
"""

from __future__ import annotations

# ---- Model + validation seams (tests monkeypatch these) ----------------------
# HandProfile/validate_profile are expected to be available here so tests can do:
#   monkeypatch.setattr(profile_wizard, "HandProfile", DummyHandProfile)
# and so the wizard uses the patched symbol.

from .hand_profile import HandProfile, validate_profile

# ---- I/O seams (tests monkeypatch these) ------------------------------------

# These are imported from wizard_io but re-exported here so tests can patch
# `bridge_engine.profile_wizard._input_int` and wizard code will see it.

from . import wizard_flow

from .wizard_io import (  # type: ignore
    clear_screen,
    _input_with_default,
    _input_int,
    _input_choice,
    _yes_no,
    _yes_no_help,
)

# ---- Wizard flow / builders -------------------------------------------------

# Entry points: create_profile_interactive and edit_constraints_interactive
# are defined locally below (they delegate to wizard_flow._build_profile).

# Internal helpers used by unit tests:
from .wizard_flow import (  # type: ignore
    _build_suit_range_for_prompt,
    _build_standard_constraints,
    _build_seat_profile,
    _build_profile,
)

# Note: _build_card/hcp/ace/king/queen/jack_range_for_prompt helpers were
# removed in earlier cleanup.  Tests that need range builders should use
# _build_suit_range_for_prompt (re-exported above) directly.


def create_profile_interactive() -> HandProfile:
    """
    Top-level helper for creating a new profile interactively.

    New profile behaviour:

      • User answers *metadata only* (name, description, tag, dealer,
        order, author, version, rotate flag).
      • Wizard attaches Base-style standard constraints in the background.
      • NS behaviour defaults to 'no_driver_no_index' so there is
        NO NS driver semantics and NO index matching until you
        explicitly edit the profile later.
    """
    clear_screen()
    print("=== Create New Profile ===")
    print()

    # Build all kwargs (metadata + default standard constraints)
    kwargs = wizard_flow._build_profile(existing=None)

    # Force backwards-compatible NS default for brand-new profiles:
    # treat them as "no driver / no index" unless explicitly changed later.
    kwargs["ns_role_mode"] = "no_driver_no_index"

    # Construct profile object from kwargs
    profile = HandProfile(**kwargs)

    # Validate (this may normalise weights etc., but ns_role_mode is now fixed)
    validate_profile(profile)

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

    # Prompt for new metadata via the create flow (existing=None),
    # then override constraints with the template's constraints.
    kwargs = _build_profile(existing=None, original_path=None)

    # Replace auto-generated standard constraints with the template's.
    kwargs["seat_profiles"] = dict(existing.seat_profiles)
    kwargs["subprofile_exclusions"] = list(getattr(existing, "subprofile_exclusions", []))
    kwargs["ns_role_mode"] = getattr(existing, "ns_role_mode", "no_driver_no_index")

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
    "_input_choice",
    "_yes_no",
    "_yes_no_help",
    # entrypoints
    "create_profile_interactive",
    "edit_constraints_interactive",
    # tested builders
    "_build_suit_range_for_prompt",
    "_build_standard_constraints",
    "_build_seat_profile",
]
