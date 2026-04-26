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


def _rotate_subprofile_contingents(sub: dict[str, Any]) -> None:
    """Rotate seat references inside a single subprofile dict (in place)."""
    pc = sub.get("partner_contingent_constraint")
    if isinstance(pc, dict) and "partner_seat" in pc:
        pc["partner_seat"] = _rotate_seat(pc["partner_seat"])
    oc = sub.get("opponents_contingent_suit_constraint")
    if isinstance(oc, dict) and "opponent_seat" in oc:
        oc["opponent_seat"] = _rotate_seat(oc["opponent_seat"])


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

    # seat_profiles: rekey by R(seat), and update inner `seat` field
    if "seat_profiles" in out and isinstance(out["seat_profiles"], dict):
        rekeyed: dict[str, Any] = {}
        for src_seat, sp in out["seat_profiles"].items():
            new_seat = _rotate_seat(src_seat)
            sp["seat"] = new_seat
            for sub in sp.get("subprofiles", []):
                if isinstance(sub, dict):
                    _rotate_subprofile_contingents(sub)
            rekeyed[new_seat] = sp
        out["seat_profiles"] = rekeyed

    # subprofile_exclusions: rotate each entry's seat
    if "subprofile_exclusions" in out and isinstance(out["subprofile_exclusions"], list):
        for entry in out["subprofile_exclusions"]:
            if isinstance(entry, dict) and "seat" in entry:
                entry["seat"] = _rotate_seat(entry["seat"])

    return out
