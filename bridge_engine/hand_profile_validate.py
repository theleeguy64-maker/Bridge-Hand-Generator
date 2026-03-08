from __future__ import annotations

from dataclasses import is_dataclass, fields
from typing import Any, Dict, List, Set

from .hand_profile_model import HandProfile, ProfileError


def _to_raw_dict(data: Any) -> Dict[str, Any]:
    """
    Normalise input to a plain dict that can be passed into HandProfile.from_dict.

    Accepts:
    - A HandProfile instance
    - A mapping (e.g. dict) as loaded from JSON
    """
    if isinstance(data, HandProfile):
        raw = data.to_dict()  # type: ignore[assignment]
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
        # fields() raises TypeError for non-dataclass objects.
        # Fall back to dir() probing below.
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
    if not profile.seat_profiles:
        return

    for seat_name, seat_profile in profile.seat_profiles.items():
        subprofiles = seat_profile.subprofiles
        if not subprofiles:
            continue

        for sub_idx, sub in enumerate(subprofiles, start=1):
            rs = sub.random_suit_constraint
            if rs is None:
                continue

            # SubProfile.standard is typed as StandardSuitConstraints (non-optional),
            # but guard against None for test mocks that omit it.
            std = sub.standard
            if std is None:
                continue

            # Map standard suit ranges by suit symbol
            std_by_suit = {
                "S": std.spades,
                "H": std.hearts,
                "D": std.diamonds,
                "C": std.clubs,
            }

            # allowed_suits and suit_ranges are validated non-empty by
            # RandomSuitConstraintData.__post_init__, so no fallbacks needed.
            allowed_suits = rs.allowed_suits
            suit_ranges = rs.suit_ranges

            # Pair suits with ranges (ignore any extra suits beyond ranges)
            for suit_symbol, rs_range in zip(allowed_suits, suit_ranges):
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
                raise ProfileError(f"Subprofile #{idx} on seat {seat!r} must be a dict")
            w_raw = sp_dict.get("weight_percent", 0.0)
            try:
                w = float(w_raw)
            except (TypeError, ValueError):
                raise ProfileError(f"Subprofile weight_percent on seat {seat!r} must be numeric; got {w_raw!r}")
            if w < 0.0:
                raise ProfileError(f"Subprofile weight_percent on seat {seat!r} must be non-negative; got {w}")
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
            raise ProfileError(f"Subprofile weights on seat {seat!r} must sum to approximately 100 (got {total:.2f}).")

        # Rescale so the sum is exactly 100.0, and close rounding on the last.
        factor = 100.0 / total
        running = 0.0
        for sp_dict, w in zip(sub_list[:-1], weights[:-1]):
            new_w = w * factor
            sp_dict["weight_percent"] = new_w
            running += new_w

        # Last one takes the slack so we hit 100.0 exactly.
        sub_list[-1]["weight_percent"] = 100.0 - running


def _validate_partner_contingent(profile: HandProfile) -> None:
    """
    Ensure that for any subprofile with a partner-contingent constraint,
    the referenced *partner seat* has a Random-Suit (RS) constraint.

    At runtime, `_build_processing_order()` always processes RS seats
    before non-RS seats, so an RS constraint on the partner guarantees
    the partner's suit choices are visible when the PC seat is dealt.

    We do NOT rely on `hand_dealing_order` (a display hint only).
    """
    for seat, seat_profile in profile.seat_profiles.items():
        for sub in seat_profile.subprofiles:
            constraint = sub.partner_contingent_constraint
            if constraint is None:
                continue

            seats = _extract_seat_names_from_constraint(constraint)
            if not seats:
                # Nothing we can check – be lenient.
                continue

            partner_seat = seats[0]

            # Partner seat must exist in the profile.
            if partner_seat not in profile.seat_profiles:
                raise ProfileError(
                    f"Partner seat {partner_seat!r} referenced from {seat!r} is not defined in seat_profiles."
                )

            # Partner seat must have an RS constraint on at least one
            # subprofile, so the runtime processing order guarantees it
            # is dealt before the PC seat.
            partner_sp = profile.seat_profiles[partner_seat]
            has_rs = any(s.random_suit_constraint is not None for s in partner_sp.subprofiles)
            if not has_rs:
                raise ProfileError(
                    f"Partner seat {partner_seat} must have a Random-Suit "
                    f"constraint so it is processed before {seat} for "
                    f"partner-contingent constraints."
                )

            # When use_non_chosen_suit is True, the partner must have an
            # RS constraint with exactly 1 non-chosen suit
            # (allowed_suits - required_suits_count == 1).
            # Note: partner_seat existence already validated above (line 405).
            if constraint.use_non_chosen_suit:
                has_exactly_one_non_chosen = False
                for partner_sub in partner_sp.subprofiles:
                    rs = partner_sub.random_suit_constraint
                    if rs is not None:
                        surplus = len(rs.allowed_suits) - rs.required_suits_count
                        if surplus == 1:
                            has_exactly_one_non_chosen = True
                            break
                if not has_exactly_one_non_chosen:
                    raise ProfileError(
                        f"Seat {seat!r} uses non-chosen-suit PC, but partner "
                        f"{partner_seat!r} does not have an RS constraint with "
                        f"exactly 1 non-chosen suit (allowed - required must be 1)."
                    )


def _validate_opponent_contingent(profile: HandProfile) -> None:
    """
    Structural sanity checks for opponents-contingent constraints.

    For each OC subprofile, every referenced opponent seat must:
    1. Exist in seat_profiles.
    2. Have a Random-Suit (RS) constraint on at least one subprofile.

    At runtime, `_build_processing_order()` always processes RS seats
    before non-RS seats, so an RS constraint on the opponent guarantees
    the opponent's suit choices are visible when the OC seat is dealt.

    We do NOT rely on `hand_dealing_order` (a display hint only).
    """
    for seat, seat_profile in profile.seat_profiles.items():
        for sub in seat_profile.subprofiles:
            constraint = sub.opponents_contingent_suit_constraint
            if constraint is None:
                continue

            opp_seats = _extract_seat_names_from_constraint(constraint)
            if not opp_seats:
                # Nothing concrete to validate – be lenient.
                continue

            for opp in opp_seats:
                # Opponent seat must exist in the profile.
                if opp not in profile.seat_profiles:
                    raise ProfileError(
                        f"Opponent seat {opp!r} referenced from {seat!r} is not defined in seat_profiles."
                    )

                # Opponent seat must have an RS constraint on at least one
                # subprofile, so runtime processing order guarantees it is
                # dealt before the OC seat.
                opp_sp = profile.seat_profiles[opp]
                has_rs = any(s.random_suit_constraint is not None for s in opp_sp.subprofiles)
                if not has_rs:
                    raise ProfileError(
                        f"Opponent seat {opp} must have a Random-Suit "
                        f"constraint so it is processed before {seat} for "
                        f"opponents-contingent constraints."
                    )

            # When use_non_chosen_suit is True, the opponent must have an
            # RS constraint with exactly 1 non-chosen suit
            # (allowed_suits - required_suits_count == 1).
            # Multi-suit non-chosen is not yet supported.
            # Note: opp_seats non-empty (guarded at line 464) and each
            # element validated in loop above (line 470).
            if constraint.use_non_chosen_suit:
                opp_seat_key = opp_seats[0]
                opp_sp = profile.seat_profiles[opp_seat_key]
                has_exactly_one_non_chosen = False
                for opp_sub in opp_sp.subprofiles:
                    rs = opp_sub.random_suit_constraint
                    if rs is not None:
                        surplus = len(rs.allowed_suits) - rs.required_suits_count
                        if surplus == 1:
                            has_exactly_one_non_chosen = True
                            break
                if not has_exactly_one_non_chosen:
                    raise ProfileError(
                        f"Seat {seat!r} uses non-chosen-suit OC, but opponent "
                        f"{opp_seat_key!r} does not have an RS constraint with "
                        f"exactly 1 non-chosen suit (allowed - required must be 1)."
                    )


def _validate_linked_profile(profile: HandProfile) -> None:
    """
    Validate ns_linked_profile and ew_linked_profile on a HandProfile.

    For each linked profile (when not None):
      1. Primary seat must be valid for the pair (N/S for NS, E/W for EW).
      2. Both seats must have at least 2 subprofiles.
      3. All primary indices (keys) must be valid: 0 <= key < len(primary_seat.subprofiles).
      4. All secondary indices (values) must be valid: 0 <= idx < len(secondary_seat.subprofiles).
      5. Every primary sub index must be a key (exhaustive for primary).
      6. Every secondary sub index must appear in at least one value list (surjective).
      7. No empty value lists.
    """
    from .hand_profile_model import LinkedProfile

    for pair_label, linked in [
        ("NS", getattr(profile, "ns_linked_profile", None)),
        ("EW", getattr(profile, "ew_linked_profile", None)),
    ]:
        if linked is None:
            continue
        if not isinstance(linked, LinkedProfile):
            continue

        # 1. Primary seat must be valid for the pair.
        valid_primaries = ("N", "S") if pair_label == "NS" else ("E", "W")
        if linked.primary_seat not in valid_primaries:
            raise ProfileError(
                f"{pair_label} linked profile: primary_seat must be one of "
                f"{valid_primaries}, got {linked.primary_seat!r}."
            )

        primary_seat = linked.primary_seat
        secondary_seat = linked.secondary_seat()

        primary_sp = profile.seat_profiles.get(primary_seat)
        secondary_sp = profile.seat_profiles.get(secondary_seat)

        # 2. Both seats must have seat profiles with ≥2 subprofiles.
        if primary_sp is None or secondary_sp is None:
            raise ProfileError(
                f"{pair_label} linked profile requires both {primary_seat} and {secondary_seat} to have seat profiles."
            )
        if len(primary_sp.subprofiles) < 2:
            raise ProfileError(
                f"{pair_label} linked profile: primary seat {primary_seat} must have "
                f"at least 2 subprofiles (has {len(primary_sp.subprofiles)})."
            )
        if len(secondary_sp.subprofiles) < 2:
            raise ProfileError(
                f"{pair_label} linked profile: secondary seat {secondary_seat} must have "
                f"at least 2 subprofiles (has {len(secondary_sp.subprofiles)})."
            )

        smap = linked.subprofile_map
        num_primary = len(primary_sp.subprofiles)
        num_secondary = len(secondary_sp.subprofiles)

        # 3. Validate primary index keys.
        for key in smap:
            if not (0 <= key < num_primary):
                raise ProfileError(
                    f"{pair_label} linked profile: primary index {key} out of bounds "
                    f"(primary seat {primary_seat} has {num_primary} subprofiles)."
                )

        # 4. Validate secondary index values.
        for key, sec_indices in smap.items():
            for idx in sec_indices:
                if not (0 <= idx < num_secondary):
                    raise ProfileError(
                        f"{pair_label} linked profile: secondary index {idx} "
                        f"(for primary key {key}) out of bounds "
                        f"(secondary seat {secondary_seat} has {num_secondary} subprofiles)."
                    )

        # 5. Every primary sub index must be a key (exhaustive).
        for i in range(num_primary):
            if i not in smap:
                raise ProfileError(
                    f"{pair_label} linked profile: primary sub index {i} is missing "
                    f"as a key (all {num_primary} primary sub indices must be present)."
                )

        # 6. Every secondary sub index must appear in at least one value list (surjective).
        all_secondary: Set[int] = set()
        for vals in smap.values():
            all_secondary.update(vals)
        for i in range(num_secondary):
            if i not in all_secondary:
                raise ProfileError(
                    f"{pair_label} linked profile: secondary sub index {i} does not "
                    f"appear in any primary's mapping (all secondary subs must be reachable)."
                )

        # 7. No empty value lists.
        for key, vals in smap.items():
            if not vals:
                raise ProfileError(
                    f"{pair_label} linked profile: primary key {key} has an empty secondary mapping list."
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

    # -----------------------------------
    # 3. Subprofile weight normalisation
    # -----------------------------------
    _normalise_subprofile_weights(raw)

    # -----------------------------------
    # 4. Build HandProfile from normalised dict
    # -----------------------------------
    profile = HandProfile.from_dict(raw)

    # -----------------------------------
    # 5. Structural validations that rely on HandProfile objects
    # -----------------------------------
    _validate_partner_contingent(profile)
    _validate_opponent_contingent(profile)

    # Random Suit vs standard suit constraints consistency
    _validate_random_suit_vs_standard(profile)

    # Linked profile validation
    _validate_linked_profile(profile)

    # 7. Seat-level viability check (light + cross-seat dead subprofile detection)
    # validate_profile_viability() calls the light check first, then NS coupling,
    # then cross-seat HCP/card feasibility to detect dead subprofiles.
    # Late import to break circular dependency:
    #   seat_viability → hand_profile → hand_profile_validate → profile_viability → seat_viability
    from .profile_viability import validate_profile_viability  # noqa: E402

    validate_profile_viability(profile)

    # 8. Validate subprofile exclusions (if present)
    for exc in profile.subprofile_exclusions:
        exc.validate(profile)

    # IMPORTANT: callers expect the validated HandProfile back
    return profile
