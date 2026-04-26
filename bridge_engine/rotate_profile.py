"""Rotate a HandProfile around the table (W→N→E→S→W).

Pure data transformation: every seat reference advances one position around
the cycle. See docs/superpowers/specs/2026-04-25-rotate-profile-design.md
for the full rule set.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

from bridge_engine import profile_store
from bridge_engine.hand_profile_model import ProfileError
from bridge_engine.hand_profile_validate import validate_profile
from bridge_engine.profile_cli import _safe_file_stem

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


def _swap_and_rotate_linked(out: dict[str, Any]) -> None:
    """Swap ns↔ew slots and rotate primary_seat inside each (in place)."""
    ns = out.get("ns_linked_profile")
    ew = out.get("ew_linked_profile")
    if isinstance(ns, dict) and "primary_seat" in ns:
        ns["primary_seat"] = _rotate_seat(ns["primary_seat"])
    if isinstance(ew, dict) and "primary_seat" in ew:
        ew["primary_seat"] = _rotate_seat(ew["primary_seat"])
    out["ns_linked_profile"] = ew
    out["ew_linked_profile"] = ns


_PRONOUN_PAIRS = (("Our", "We"), ("our", "we"))
# After normalisation, swap rules (all fire simultaneously via sentinels):
#   Opps → We  |  We → Opps  |  we → Opps
_SWAP_RULES: tuple[tuple[str, str], ...] = (
    ("Opps", "We"),
    ("We", "Opps"),
    ("we", "Opps"),
)


def _swap_pronouns(name: str) -> str:
    """Two-step pronoun swap on a profile_name string.

    1. Normalise: Our/our → We/we (whole-word).
    2. Swap (simultaneous via sentinels): Opps↔We, We→Opps, we→Opps.
    """
    s = name
    for src, dst in _PRONOUN_PAIRS:
        s = re.sub(rf"\b{src}\b", dst, s)
    # Replace each source with a unique sentinel first.
    for src, _dst in _SWAP_RULES:
        s = re.sub(rf"\b{re.escape(src)}\b", f"__ROT_{src}__", s)
    # Then resolve all sentinels to their targets.
    for src, dst in _SWAP_RULES:
        s = s.replace(f"__ROT_{src}__", dst)
    return s


def _derived_output_path(profile_name: str, profiles_dir: Path) -> Path:
    """Filename = '<safe_stem>_v0.1.json' inside profiles_dir."""
    stem = _safe_file_stem(profile_name)
    return profiles_dir / f"{stem}_v0.1.json"


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
    # Guard ordering: already-rotated check runs first, so a source with both
    # rotated_from set AND no swappable pronouns still gets the more specific
    # "already rotated" error rather than the generic pronoun message.
    if profile_dict.get("rotated_from"):
        raise ProfileError(
            f"Source is already a rotated profile (rotated_from: {profile_dict['rotated_from']!r}); rotation refused."
        )

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

    # profile_name swap (or override)
    if new_name is not None:
        out["profile_name"] = new_name
    else:
        original = out.get("profile_name", "")
        swapped = _swap_pronouns(original)
        if swapped == original:
            raise ProfileError(
                "Source profile_name does not contain Opps/We/Our pronouns to swap; supply --name explicitly."
            )
        out["profile_name"] = swapped

    if new_description is not None:
        out["description"] = new_description

    _swap_and_rotate_linked(out)

    return out


def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m bridge_engine.rotate_profile",
        description="Rotate a hand profile around the table (W→N→E→S→W).",
    )
    p.add_argument("input", help="Path to the source profile JSON file.")
    p.add_argument(
        "--name", dest="new_name", default=None, help="Override the rotated profile_name (bypasses the pronoun swap)."
    )
    p.add_argument("--description", dest="new_description", default=None, help="Override the rotated description.")
    p.add_argument("--output", dest="output", default=None, help="Override the derived output path.")
    p.add_argument("--force", action="store_true", help="Overwrite the output file if it already exists.")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_argparser().parse_args(argv)

    src_path = Path(args.input)
    try:
        with src_path.open("r", encoding="utf-8") as f:
            src_dict = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError) as e:
        print(f"Cannot read input: {e}", file=sys.stderr)
        return 1

    try:
        rotated = rotate_profile(src_dict, new_name=args.new_name, new_description=args.new_description)
    except ProfileError as e:
        print(str(e), file=sys.stderr)
        return 2

    rotated["rotated_from"] = src_path.name

    try:
        validate_profile(rotated)
    except (ProfileError, KeyError, TypeError, ValueError) as e:
        print(f"Rotation produced invalid profile: {e}", file=sys.stderr)
        return 2

    profiles_dir = profile_store._profiles_dir()
    out_path = (
        Path(args.output) if args.output is not None else _derived_output_path(rotated["profile_name"], profiles_dir)
    )
    if out_path.exists() and not args.force:
        print(f"Output exists: {out_path}. Pass --force to overwrite.", file=sys.stderr)
        return 4

    profile_store._atomic_write(out_path, json.dumps(rotated, indent=2, sort_keys=True) + "\n")

    src = src_dict.get("dealer", "?")
    print(
        f"Rotated: dealer {src} → {rotated.get('dealer', '?')}, "
        f"NS↔EW linked profiles swapped, "
        f"{len(rotated.get('seat_profiles', {}))} seat profiles rekeyed. "
        f"Wrote {out_path}."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
