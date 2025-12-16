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
)

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
