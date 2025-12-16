from __future__ import annotations

from typing import Any, Dict, List, Optional

import math

from .hand_profile_model import HandProfile, ProfileError, RandomSuitConstraintData

def _build_order_index(profile: HandProfile) -> dict[str, int]:
    return {seat: i for i, seat in enumerate(profile.hand_dealing_order)}


def _validate_partner_contingent_constraints(
    profile: HandProfile,
    order_index: dict[str, int],
) -> None:
    for seat, seat_profile in profile.seat_profiles.items():
        for sub in seat_profile.subprofiles:
            pc = sub.partner_contingent_constraint
            if pc is None:
                continue

            partner = pc.partner_seat
            partner_profile = profile.seat_profiles.get(partner)
            if partner_profile is None:
                raise ProfileError(
                    f"Partner contingent on seat {seat} refers to missing seat {partner}."
                )

            if not any(
                sp.random_suit_constraint is not None
                for sp in partner_profile.subprofiles
            ):
                raise ProfileError(
                    f"Partner contingent on seat {seat} requires partner {partner} "
                    "to have a Random Suit constraint."
                )

            if order_index[partner] > order_index[seat]:
                raise ProfileError(
                    f"Partner contingent seat {seat} must be dealt after partner {partner}."
                )


def _validate_opponent_contingent_constraints(
    profile: HandProfile,
    order_index: dict[str, int],
) -> None:
    for seat, seat_profile in profile.seat_profiles.items():
        for sub in seat_profile.subprofiles:
            oc = getattr(sub, "opponents_contingent_suit_constraint", None)
            if oc is None:
                continue

            opponent = oc.opponent_seat
            opp_profile = profile.seat_profiles.get(opponent)
            if opp_profile is None:
                raise ProfileError(
                    f"Opponent contingent on seat {seat} refers to missing seat {opponent}."
                )

            if not any(
                sp.random_suit_constraint is not None
                for sp in opp_profile.subprofiles
            ):
                raise ProfileError(
                    f"Opponent contingent on seat {seat} requires opponent {opponent} "
                    "to have a Random Suit constraint."
                )

            if order_index[opponent] > order_index[seat]:
                raise ProfileError(
                    f"Opponent contingent seat {seat} must be dealt after opponent {opponent}."
                )

# ---------------------------------------------------------------------------
# Top-level validation helper (used by tests / loaders)
# ---------------------------------------------------------------------------


def validate_profile(data: Any) -> HandProfile:
    # --- F5 legacy normalization shim ---
    if isinstance(data, dict):
        data = dict(data)
        schema_version = int(data.get("schema_version", 0))
        if schema_version == 0:
            data.setdefault("rotate_deals_by_default", True)
            data.setdefault("subprofile_exclusions", [])
    # --- end legacy normalization ---

    """
    Validate a profile whether given as a dict or an existing HandProfile.

    This runs:
      - cross-seat Partner / Opponents Contingent → Random Suit checks
      - dealing-order constraints that the partner/opponent must be dealt BEFORE the contingent seat
      - weighted SubProfile validation/normalization (weight_percent sums to ~100)
      - lightweight RandomSuitConstraintData structural checks (no .validate() method required)
    """
    # Normalize input to a HandProfile instance
    if isinstance(data, HandProfile):
        profile = data
    elif isinstance(data, dict):
        profile = HandProfile.from_dict(data)
    else:
        raise ProfileError(
            f"validate_profile() requires a dict or HandProfile, got {type(data)}"
        )

    # Precompute dealing order positions for partner order checks
    order_index = {seat: idx for idx, seat in enumerate(profile.hand_dealing_order)}

    # ------------------------------------------------------------------
    # Cross-seat contingent checks
    # ------------------------------------------------------------------
    for seat, seat_profile in profile.seat_profiles.items():
        for sub in seat_profile.subprofiles:
            # Partner Contingent → Random Suit
            pc = sub.partner_contingent_constraint
            if pc is not None:
                partner = pc.partner_seat
                partner_profile = profile.seat_profiles.get(partner)
                if partner_profile is None:
                    raise ProfileError(
                        "Partner contingent constraint on seat "
                        f"{seat} refers to missing partner seat {partner}."
                    )

                has_random = any(
                    sp.random_suit_constraint is not None
                    for sp in partner_profile.subprofiles
                )
                if not has_random:
                    raise ProfileError(
                        "Partner contingent constraint on seat "
                        f"{seat} refers to partner seat {partner}, "
                        "which has no sub-profile with a Random Suit constraint."
                    )

                if partner not in order_index or seat not in order_index:
                    raise ProfileError(
                        "Partner contingent constraint involves seat(s) not in "
                        "hand_dealing_order."
                    )
                if order_index[partner] > order_index[seat]:
                    raise ProfileError(
                        "Partner contingent seat must be dealt after its partner. "
                        f"Seat {seat} (partner={partner}) violates dealing order "
                        f"{profile.hand_dealing_order}."
                    )

            # Opponents Contingent-Suit → Random Suit (if present)
            oc = getattr(sub, "opponents_contingent_suit_constraint", None)
            if oc is not None:
                opponent = oc.opponent_seat
                opp_profile = profile.seat_profiles.get(opponent)
                if opp_profile is None:
                    raise ProfileError(
                        "Opponents contingent constraint on seat "
                        f"{seat} refers to missing opponent seat {opponent}."
                    )

                has_random_opp = any(
                    sp.random_suit_constraint is not None
                    for sp in opp_profile.subprofiles
                )
                if not has_random_opp:
                    raise ProfileError(
                        "Opponents contingent constraint on seat "
                        f"{seat} refers to opponent seat {opponent}, "
                        "which has no sub-profile with a Random Suit constraint."
                    )

                if opponent not in order_index or seat not in order_index:
                    raise ProfileError(
                        "Opponents contingent constraint involves seat(s) not in "
                        "hand_dealing_order."
                    )
                if order_index[opponent] > order_index[seat]:
                    raise ProfileError(
                        "Opponents contingent seat must be dealt after its opponent. "
                        f"Seat {seat} (opponent={opponent}) violates dealing order "
                        f"{profile.hand_dealing_order}."
                    )

       # ------------------------------------------------------------------
    # Phase 2: weighted SubProfiles per seat (weight_percent in %)
    # ------------------------------------------------------------------

    for seat, seat_profile in profile.seat_profiles.items():
        subprofiles = list(getattr(seat_profile, "subprofiles", []))
        if not subprofiles:
            continue

        # Extract weights, treating missing attribute as 0.0
        weights: List[float] = []
        for sp in subprofiles:
            w = getattr(sp, "weight_percent", 0.0)
            # Coerce to float defensively
            try:
                w = float(w)
            except (TypeError, ValueError):
                raise ProfileError(
                    f"Seat {seat}: weight_percent must be numeric, got {w!r}."
                )
            weights.append(w)

        total = sum(weights)

        # Legacy / unset case: all weights are 0.0 → auto-equalise to 100/N
        if math.isclose(total, 0.0, abs_tol=1e-9):
            n = len(subprofiles)
            raw = 100.0 / n
            base = math.floor(raw * 10.0) / 10.0  # one decimal, rounded down
            equal_weights = [base] * n
            sum_so_far = base * n
            remaining = round(100.0 - sum_so_far, 1)

            # Distribute remaining 0.1 increments deterministically
            i = 0
            while remaining > 1e-9:
                equal_weights[i] = round(equal_weights[i] + 0.1, 1)
                remaining = round(remaining - 0.1, 1)
                i = (i + 1) % n

            # Write back to frozen dataclass
            for sp, w in zip(subprofiles, equal_weights):
                object.__setattr__(sp, "weight_percent", w)
            weights = equal_weights
            total = sum(weights)

        # 1) No negatives, at most 1 decimal place
        for sp in subprofiles:
            w = float(getattr(sp, "weight_percent", 0.0))
            if w < 0.0:
                raise ProfileError(
                    f"Seat {seat}: weight_percent must be non-negative, got {w}."
                )
            scaled = w * 10.0
            if not math.isclose(scaled, round(scaled), abs_tol=1e-6):
                raise ProfileError(
                    f"Seat {seat}: weight_percent must have at most one decimal "
                    f"place, got {w}."
                )

        weights = [float(sp.weight_percent) for sp in subprofiles]
        total = sum(weights)

        # 2) Sum must be ~100; if within 2%, normalise; else reject.
        if not math.isclose(total, 100.0, abs_tol=1e-6):
            if abs(total - 100.0) <= 2.0 and total > 0.0:
                scale = 100.0 / total
                scaled = [w * scale for w in weights]
                rounded = [round(w, 1) for w in scaled]
                norm_total = sum(rounded)

                drift = round(100.0 - norm_total, 1)
                i = 0
                step = 0.1 if drift > 0 else -0.1
                while abs(drift) > 1e-9:
                    rounded[i] = round(rounded[i] + step, 1)
                    drift = round(drift - step, 1)
                    i = (i + 1) % len(rounded)

                for sp, w in zip(subprofiles, rounded):
                    object.__setattr__(sp, "weight_percent", w)
            else:
                raise ProfileError(
                    f"Seat {seat}: subprofile weights must sum to 100.0, got "
                    f"{total:.1f}."
                )

        # Validate random-suit constraints if present (lightweight + backwards compatible).
        for sub in subprofiles:
            rsc = getattr(sub, "random_suit_constraint", None)
            if not isinstance(rsc, RandomSuitConstraintData):
                continue

            allowed = getattr(rsc, "allowed_suits", None)
            if not allowed:
                raise ProfileError(
                    f"Seat {seat}: Random-suit constraint must specify at least one suit."
                )

            # Ranges may be stored under either name depending on version.
            ranges = getattr(rsc, "ranges", None)
            if ranges is None:
                ranges = getattr(rsc, "suit_ranges", None)

            if not isinstance(ranges, (list, tuple)) or len(ranges) == 0:
                raise ProfileError(
                    f"Seat {seat}: Random-suit constraint must have at least one SuitRange."
                )

            # Required count may be stored under different names; default to 1.
            required_count = getattr(rsc, "num_required", None)
            if required_count is None:
                required_count = getattr(rsc, "required_suits_count", 1)

            try:
                required_count = int(required_count)
            except (TypeError, ValueError):
                raise ProfileError(
                    f"Seat {seat}: Random-suit required count must be an integer, got {required_count!r}."
                )

            if required_count < 1 or required_count > len(allowed):
                raise ProfileError(
                    f"Seat {seat}: Random-suit required_count={required_count} "
                    f"is inconsistent with allowed_suits={allowed}."
                )

            # Enforce that SuitRange entries match the required count.
            if len(ranges) != required_count:
                raise ProfileError(
                    f"Seat {seat}: Random-suit has {len(ranges)} SuitRange entries "
                    f"but required_count={required_count}."
                )

    # Validate subprofile exclusions (if present)
    for exc in getattr(profile, "subprofile_exclusions", []):
        exc.validate(profile)

    # If we got here, everything is valid
    return profile