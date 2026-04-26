"""Rotate a HandProfile around the table (W→N→E→S→W).

Pure data transformation: every seat reference advances one position around
the cycle. See docs/superpowers/specs/2026-04-25-rotate-profile-design.md
for the full rule set.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

ROTATE_MAP: dict[str, str] = {"W": "N", "N": "E", "E": "S", "S": "W"}

_LEGACY_KEYS = ("ns_role_mode", "ew_role_mode", "ns_bespoke_map", "ew_bespoke_map")


def _rotate_seat(seat: str) -> str:
    if seat not in ROTATE_MAP:
        raise ValueError(f"Invalid seat: {seat!r}")
    return ROTATE_MAP[seat]


def rotate_profile(
    profile_dict: dict[str, Any],
    *,
    new_name: str | None = None,
    new_description: str | None = None,
) -> dict[str, Any]:
    """Return a rotated deep copy of profile_dict.

    The input dict is never mutated. Every seat reference advances one
    position around the cycle W→N→E→S→W. See the module docstring for
    the full rule set.
    """
    out = deepcopy(profile_dict)

    # Top-level seat fields
    if "dealer" in out:
        out["dealer"] = _rotate_seat(out["dealer"])
    if "hand_dealing_order" in out and isinstance(out["hand_dealing_order"], list):
        out["hand_dealing_order"] = [_rotate_seat(s) for s in out["hand_dealing_order"]]

    # Strip legacy keys
    for key in _LEGACY_KEYS:
        out.pop(key, None)

    # Reset version
    out["version"] = "0.1"

    # Subprofiles, exclusions, linked profiles — TODO: subsequent tasks.
    return out
