from __future__ import annotations

from dataclasses import asdict, is_dataclass, fields
from typing import Any, Dict, List

from .hand_profile_model import HandProfile, SeatProfile, SubProfile, ProfileError

from .seat_viability import validate_profile_viability_light
from .profile_viability import validate_profile_viability

# Type alias for seat names (N, E, S, W)
Seat = str


def _to_raw_dict(data: Any) -> Dict[str, Any]:
    """
    Normalise input to a plain dict that can be passed into HandProfile.from_dict.

    Accepts:
    - A HandProfile instance
    - A mapping (e.g. dict) as loaded from JSON
    """
    if isinstance(data, HandProfile):
        # Prefer a bespoke serialiser if it exists.
        if hasattr(data, "to_dict"):
            raw = data.to_dict()  # type: ignore[assignment]
        else:
            raw = asdict(data)
        if not isinstance(raw, dict):
            raise TypeError("HandProfile.to_dict() must return a mapping")
        return dict(raw)

    if isinstance(data, dict):
        # Shallow copy so we don't mutate caller's data.
        return dict(data)

    raise TypeError("Profile data must be a dict-like object or HandProfile")


def _extract_seat_names_from_constraint(constraint: Any) -> List[str]:
    """
    Best-effort helper to pull any seat names from a constraint object.

    This is intentionally generic so it works for both PartnerContingentData and
    OpponentsContingentSuitData without hard-coding their exact field names.
    """
    seats: List[str] = []

    # 1) Dataclass fields are the most reliable.
    try:
        if is_dataclass(constraint):
            for f in fields(constraint):
                name = f.name
                if "seat" not in name:
                    continue
                val = getattr(constraint, name, None)
                if isinstance(val, str):
                    seats.append(val)
                elif isinstance(val, (list, tuple, set)):
                    seats.extend([s for s in val if isinstance(s, str)])
    except TypeError:
        # Not a dataclass – fall back to dir() probing.
        pass

    # 2) Fallback: scan attributes for anything with "seat" in the name.
    if not seats:
        for name in dir(constraint):
            if name.startswith("_") or "seat" not in name:
                continue
            try:
                val = getattr(constraint, name)
            except AttributeError:
                continue
            if isinstance(val, str):
                seats.append(val)
            elif isinstance(val, (list, tuple, set)):
                seats.extend([s for s in val if isinstance(s, str)])

    return seats

def _validate_random_suit_vs_standard(profile: HandProfile) -> None:
    """
    Sanity-check RandomSuitConstraintData against the standard suit constraints.

    For every seat / sub-profile that has a random_suit_constraint:

      • For each allowed suit S in rs.allowed_suits:
          - Treat rs.suit_ranges[...] as the effective SuitRange for S
          - Use the standard StandardSuitConstraints ranges for the other 3 suits
      • Compute the sum of min_cards across all 4 suits.
          - If sum(min_cards) > 13 → raise ProfileError.
      • Optionally check that some allocation is possible:
          - sum(max_cards) >= 13, otherwise raise ProfileError.

    IMPORTANT:
      • For legacy profiles where no standard constraints object is attached to the
        sub-profile (std is None), we *skip* this check rather than rejecting.
        Those profiles are already validated by the existing standard logic.
    """
    seat_profiles = getattr(profile, "seat_profiles", None)
    if not seat_profiles:
        return

    for seat_name, seat_profile in seat_profiles.items():
        subprofiles = getattr(seat_profile, "subprofiles", None)
        if not subprofiles:
            continue

        for sub_idx, sub in enumerate(subprofiles, start=1):
            rs = getattr(sub, "random_suit_constraint", None)
            if rs is None:
                continue

            # Try both attribute names to be robust with model evolution
            std = getattr(sub, "standard", None) or getattr(
                sub, "standard_constraints", None
            )
            if std is None:
                # Legacy / non-standard setup: do not enforce this cross-check
                continue

            # Map standard suit ranges by suit symbol
            std_by_suit = {
                "S": std.spades,
                "H": std.hearts,
                "D": std.diamonds,
                "C": std.clubs,
            }

            # If allowed_suits is empty/None, treat as all suits allowed
            allowed_suits = rs.allowed_suits or ["S", "H", "D", "C"]
            suit_ranges = rs.suit_ranges or []

            # Pair suits with ranges safely (ignore any extra)
            pairs = list(zip(allowed_suits, suit_ranges))
            if not pairs:
                # Nothing concrete to check
                continue

            for suit_symbol, rs_range in pairs:
                if suit_symbol not in std_by_suit:
                    # Unexpected but don't crash; skip this suit
                    continue

                # Effective ranges per suit: Random Suit range overrides the standard one
                eff_ranges = dict(std_by_suit)
                eff_ranges[suit_symbol] = rs_range

                total_min = sum(r.min_cards for r in eff_ranges.values())
                total_max = sum(r.max_cards for r in eff_ranges.values())

                if total_min > 13:
                    raise ProfileError(
                        f"Seat {seat_name} sub-profile {sub_idx}: "
                        f"Random Suit + standard suit constraints are impossible for suit "
                        f"{suit_symbol}: sum of min_cards = {total_min} (> 13)."
                    )

                if total_max < 13:
                    raise ProfileError(
                        f"Seat {seat_name} sub-profile {sub_idx}: "
                        f"Random Suit + standard suit constraints leave at most "
                        f"{total_max} cards across suits (< 13)."
                    )

def _normalise_subprofile_weights(raw: Dict[str, Any]) -> None:
    """
    In-place normalisation of subprofile weights on a raw profile dict.

    Rules (matching the weighted_subprofiles tests):

    - For each seat:
      - If *all* weight_percent values are 0.0 or missing:
          → set them all to 100.0 / N (equal weighting).
      - If *any* weight is negative:
          → raise ProfileError.
      - Otherwise:
          - Sum the weights:
              • If sum is not within [98, 102]:
                    → raise ProfileError.
              • Else:
                    → rescale so they sum to exactly 100.0,
                      giving the last subprofile the "slack" so
                      the total is exactly 100.0.
    """
    seat_profiles = raw.get("seat_profiles") or {}
    if not isinstance(seat_profiles, dict):
        raise ProfileError("seat_profiles must be a mapping of seat -> profile data")

    for seat, sp_data in seat_profiles.items():
        if not isinstance(sp_data, dict):
            raise ProfileError(f"Seat profile for {seat!r} must be a dict")

        sub_list = sp_data.get("subprofiles") or []
        if not sub_list:
            # No subprofiles on this seat – nothing to normalise.
            continue

        if not isinstance(sub_list, list):
            raise ProfileError(f"subprofiles for seat {seat!r} must be a list")

        # Collect weights and validate non-negativity.
        weights: List[float] = []
        for idx, sp_dict in enumerate(sub_list):
            if not isinstance(sp_dict, dict):
                raise ProfileError(
                    f"Subprofile #{idx} on seat {seat!r} must be a dict"
                )
            w_raw = sp_dict.get("weight_percent", 0.0)
            try:
                w = float(w_raw)
            except (TypeError, ValueError):
                raise ProfileError(
                    f"Subprofile weight_percent on seat {seat!r} must be numeric; "
                    f"got {w_raw!r}"
                )
            if w < 0.0:
                raise ProfileError(
                    f"Subprofile weight_percent on seat {seat!r} must be "
                    f"non-negative; got {w}"
                )
            weights.append(w)

        total = sum(weights)

        if total == 0.0:
            # Legacy case: no weights set; equalise across subprofiles.
            equal = 100.0 / len(sub_list)
            for sp_dict in sub_list:
                sp_dict["weight_percent"] = equal
            continue

        # Require "about 100" – within ±2 (see tests).
        if not (98.0 <= total <= 102.0):
            raise ProfileError(
                f"Subprofile weights on seat {seat!r} must sum to "
                f"approximately 100 (got {total:.2f})."
            )

        # Rescale so the sum is exactly 100.0, and close rounding on the last.
        factor = 100.0 / total
        running = 0.0
        for sp_dict, w in zip(sub_list[:-1], weights[:-1]):
            new_w = w * factor
            sp_dict["weight_percent"] = new_w
            running += new_w

        # Last one takes the slack so we hit 100.0 exactly.
        sub_list[-1]["weight_percent"] = 100.0 - running

def _validate_ns_role_usage_coverage(profile: HandProfile) -> None:
    """
    Ensure that for each NS seat and each role that can occur under
    ns_role_mode, there is at least one compatible SubProfile.

    ns_role_usage semantics (per SubProfile):
      - "any"           → can be used whether the seat is driver or follower
      - "driver_only"   → only usable when this seat is the NS driver
      - "follower_only" → only usable when this seat is the NS follower

    # NS sub-profile index matching: tie N/S sub-profile indices together.

    Backwards-compatible:
        - If ns_role_mode is missing → treated as "north_drives".
        - If ns_role_mode is "no_driver_no_index" → skip NS role coverage checks.
        - If ns_role_mode is unknown/future → treat as "no_driver_no_index" (skip).
        - If a SubProfile has no ns_role_usage → treated as "any".
        - If a seat has no subprofiles → skipped.
    """

    # Only relevant if N or S actually has subprofiles.
    ns_seats: list[Seat] = [
        seat
        for seat in ("N", "S")
        if seat in profile.seat_profiles
        and getattr(profile.seat_profiles[seat], "subprofiles", None)
    ]
    if not ns_seats:
        return

    # Normalise ns_role_mode with backwards-compatible default.
    #
    # Modes:
    #   - north_drives / south_drives / random_driver  → enforce ns_role_usage coverage
    #   - no_driver_no_index                           → no driver semantics, skip checks
    #
    # Back-compat:
    #   - missing/blank ns_role_mode → treated as "north_drives" (legacy behavior)
    #   - unknown/future values      → treated as "no_driver_no_index" (lenient)
    mode = getattr(profile, "ns_role_mode", "north_drives") or "north_drives"
    mode = (mode or "").strip()

    if mode in ("no_driver", "no_driver_no_index"):
        return

    if mode not in ("north_drives", "south_drives", "random_driver"):
        # Defensive: unknown future mode → disable NS role semantics rather than
        # failing profile creation.
        return

    def roles_for(seat: Seat) -> set[str]:
        """Return roles ('driver', 'follower') that this seat may take."""
        if seat not in ("N", "S"):
            return set()

        if mode == "north_drives":
            # N drives, S follows.
            return {"driver"} if seat == "N" else {"follower"}
        if mode == "south_drives":
            # S drives, N follows.
            return {"driver"} if seat == "S" else {"follower"}

        # random_driver (or unknown mapped to it):
        # either N or S may be driver or follower.
        return {"driver", "follower"}

    def has_compatible_usage(sub: SubProfile, allowed: tuple[str, str]) -> bool:
        usage = getattr(sub, "ns_role_usage", "any") or "any"
        return usage in allowed

    for seat in ("N", "S"):
        sp = profile.seat_profiles.get(seat)
        if sp is None or not getattr(sp, "subprofiles", None):
            continue

        roles = roles_for(seat)
        if not roles:
            continue

        for role in sorted(roles):
            if role == "driver":
                allowed = ("any", "driver_only")
            else:
                allowed = ("any", "follower_only")

            if not any(has_compatible_usage(sub, allowed) for sub in sp.subprofiles):
                raise ProfileError(
                    "Invalid NS role configuration: seat "
                    f"{seat} may act as {role} under ns_role_mode={mode!r}, "
                    "but no subprofile has ns_role_usage in "
                    f"{allowed}."
                )

def _validate_partner_contingent(profile: HandProfile) -> None:
    """
    Ensure that for any subprofile with a partner-contingent constraint,
    the *partner seat* is dealt *before* the seat that has the constraint.

    This matches tests like
    test_partner_must_be_dealt_before_partner_contingent.
    """
    order = list(profile.hand_dealing_order or [])
    index = {seat: i for i, seat in enumerate(order)}

    for seat, seat_profile in profile.seat_profiles.items():
        for sub in seat_profile.subprofiles:
            constraint = getattr(sub, "partner_contingent_constraint", None)
            if constraint is None:
                continue

            seats = _extract_seat_names_from_constraint(constraint)
            if not seats:
                # Nothing we can check – be lenient.
                continue

            partner_seat = seats[0]

            if partner_seat not in index:
                raise ProfileError(
                    f"Partner seat {partner_seat!r} for seat {seat!r} "
                    "is not in hand_dealing_order."
                )
            if seat not in index:
                raise ProfileError(
                    f"Seat {seat!r} has a partner-contingent constraint but "
                    "is not in hand_dealing_order."
                )

            if index[partner_seat] >= index[seat]:
                # The invalid case exercised by the test:
                # partner is dealt after the constrained hand.
                raise ProfileError(
                    f"Partner seat {partner_seat} must be dealt before {seat} "
                    "for partner-contingent constraints."
                )


def _validate_opponent_contingent(profile: HandProfile) -> None:
    """
    Structural sanity checks for opponents-contingent constraints.

    We keep this deliberately conservative:
    - If a subprofile has an opponents-contingent constraint, every
      opponent seat it references must appear in hand_dealing_order.
    - Additionally, we require those opponent seats to be dealt *before*
      the constrained seat. This matches the same deal-ordering principle
      used for partner-contingent constraints and should be compatible
      with existing golden profiles.
    """
    order = list(profile.hand_dealing_order or [])
    index = {seat: i for i, seat in enumerate(order)}

    for seat, seat_profile in profile.seat_profiles.items():
        for sub in seat_profile.subprofiles:
            constraint = getattr(sub, "opponents_contingent_suit_constraint", None)
            if constraint is None:
                continue

            opp_seats = _extract_seat_names_from_constraint(constraint)
            if not opp_seats:
                # Nothing concrete to validate – be lenient.
                continue

            if seat not in index:
                raise ProfileError(
                    f"Seat {seat!r} has an opponents-contingent constraint but "
                    "is not in hand_dealing_order."
                )

            seat_idx = index[seat]

            for opp in opp_seats:
                if opp not in index:
                    raise ProfileError(
                        f"Opponent seat {opp!r} referenced from {seat!r} is not "
                        "in hand_dealing_order."
                    )
                if index[opp] >= seat_idx:
                    raise ProfileError(
                        f"Opponent seat {opp} must be dealt before {seat} "
                        "for opponents-contingent constraints."
                    )


def validate_profile(data: Any) -> HandProfile:
    """
    Validate and normalise raw profile data, then build a HandProfile.

    Behaviour covered by tests:

    - Accepts:
        * a JSON-like dict (as loaded from disk), or
        * a HandProfile instance (used by tests)
    - Applies an F5 legacy normalisation shim for old schema_version=0 data:
        * rotate_deals_by_default defaults to True
        * subprofile_exclusions defaults to []
        * ns_role_mode defaults to "north_drives"
    - Normalises subprofile weights as per tests in test_weighted_subprofiles:
        * If all weights are 0 → equalise to 100 / N each
        * If any weight is negative → ProfileError
        * If total is within ±2 of 100 → rescale to sum to exactly 100
        * Otherwise → ProfileError
    - Delegates structural validation and conversion to HandProfile.from_dict(...)
    - Enforces partner/opponent contingent ordering constraints.
    """
    # -----------------------
    # 1. Normalise input data
    # -----------------------
    raw = _to_raw_dict(data)

    # -----------------------------------
    # 2. F5 legacy normalisation shim
    # -----------------------------------
    schema_version = int(raw.get("schema_version", 0) or 0)
    if schema_version == 0:
        # Legacy profiles: backfill missing metadata fields with sensible defaults.
        raw.setdefault("rotate_deals_by_default", True)
        raw.setdefault("subprofile_exclusions", [])
        # Backwards-compat behaviour for NS roles:
        # older JSON with no ns_role_mode should behave like
        # "no driver, no index matching" between N and S.
        raw.setdefault("ns_role_mode", "no_driver_no_index")

    # -----------------------------------
    # 3. ns_role_mode sanity (including 'no_driver_no_index')
    # -----------------------------------
    mode = str(raw.get("ns_role_mode", "no_driver_no_index") or "no_driver_no_index").strip()
    allowed_modes = {
        "north_drives",
        "south_drives",
        "random_driver",
        "no_driver",          # no driver roles, but index matching ON
        "no_driver_no_index", # no driver roles, and index matching OFF
    }
    if mode not in allowed_modes:
        mode = "no_driver_no_index"
    raw["ns_role_mode"] = mode

    # -----------------------------------
    # 4. Subprofile weight normalisation
    # -----------------------------------
    _normalise_subprofile_weights(raw)

    # -----------------------------------
    # 5. Build HandProfile from normalised dict
    # -----------------------------------
    profile = HandProfile.from_dict(raw)

    # -----------------------------------
    # 6. Structural validations that rely on HandProfile objects
    # -----------------------------------
    _validate_partner_contingent(profile)
    _validate_opponent_contingent(profile)
    _validate_ns_role_usage_coverage(profile)

    # Random Suit vs standard suit constraints consistency
    _validate_random_suit_vs_standard(profile)

    # 7. Seat-level viability check (light + cross-seat dead subprofile detection)
    # validate_profile_viability() calls the light check first, then NS coupling,
    # then cross-seat HCP/card feasibility to detect dead subprofiles.
    validate_profile_viability(profile)

    # 8. Validate subprofile exclusions (if present)
    for exc in getattr(profile, "subprofile_exclusions", []):
        exc.validate(profile)

    # IMPORTANT: callers expect the validated HandProfile back
    return profile
    