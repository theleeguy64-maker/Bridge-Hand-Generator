from __future__ import annotations
from dataclasses import replace

import pytest
import random

from bridge_engine.hand_profile import (
    SuitRange,
    StandardSuitConstraints,
    RandomSuitConstraintData,
    PartnerContingentData,
    SuitPairOverride,
    SubProfile,
    sub_label,
    SeatProfile,
    HandProfile,
    SubprofileExclusionClause,
    SubprofileExclusionData,
    validate_profile,
    ProfileError,
)


def _standard_all_open() -> StandardSuitConstraints:
    """
    Helper: completely open StandardSuitConstraints.

    Relies on SuitRange() defaults being a fully-open range,
    and on StandardSuitConstraints providing sensible defaults
    for total_min_hcp / total_max_hcp.
    """
    r = SuitRange()
    return StandardSuitConstraints(
        spades=r,
        hearts=r,
        diamonds=r,
        clubs=r,
    )


# ---------------------------------------------------------------------------
# SuitRange tests
# ---------------------------------------------------------------------------


def test_suit_range_invalid_cards_raises() -> None:
    # min_cards > max_cards should raise at construction time
    with pytest.raises(ProfileError):
        SuitRange(min_cards=10, max_cards=2)


def test_suit_range_invalid_hcp_range_raises() -> None:
    # min_hcp > max_hcp should raise at construction time
    with pytest.raises(ProfileError):
        SuitRange(min_hcp=10, max_hcp=5)


# ---------------------------------------------------------------------------
# Random suit / pair overrides / partner-contingent tests
# ---------------------------------------------------------------------------


def test_suit_pair_override_constructs_with_valid_data() -> None:
    """
    Basic sanity: SuitPairOverride can be constructed with valid suits
    and two SuitRange objects without raising.
    """
    spo = SuitPairOverride(
        suits=["S", "H"],
        first_range=SuitRange(),
        second_range=SuitRange(),
    )
    assert spo.suits == ["S", "H"]


def test_partner_contingent_requires_partner_rs() -> None:
    """
    West has a partner-contingent constraint referencing East,
    but East does NOT have a Random-Suit constraint.  Validation
    should reject this because the runtime processing order
    (`_build_processing_order`) only guarantees RS seats are dealt
    first — without RS, East's suit choices won't be visible when
    West is dealt.
    """
    north = SeatProfile(seat="N", subprofiles=[SubProfile(_standard_all_open())])
    # East has NO Random-Suit constraint — just standard.
    east = SeatProfile(
        seat="E",
        subprofiles=[SubProfile(_standard_all_open())],
    )
    south = SeatProfile(seat="S", subprofiles=[SubProfile(_standard_all_open())])
    west = SeatProfile(
        seat="W",
        subprofiles=[
            SubProfile(
                standard=_standard_all_open(),
                partner_contingent_constraint=PartnerContingentData(
                    partner_seat="E",
                    suit_range=SuitRange(),
                ),
            )
        ],
    )

    profile = HandProfile(
        profile_name="TestProfileOrder",
        description="Partner without RS",
        dealer="W",
        hand_dealing_order=["N", "E", "S", "W"],
        tag="Overcaller",
        seat_profiles={"N": north, "E": east, "S": south, "W": west},
    )

    with pytest.raises(ProfileError, match="Random-Suit"):
        validate_profile(profile)


# ---------------------------------------------------------------------------
# A reusable “minimal valid” profile
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# validate_profile / constraint tests
# ---------------------------------------------------------------------------


def test_validate_profile_valid(make_valid_profile) -> None:
    """Baseline: the constructed minimal profile should be valid."""
    profile = make_valid_profile()
    validate_profile(profile)  # should not raise


def test_standard_constraints_bad_total_hcp_range_raises() -> None:
    """
    StandardSuitConstraints with total_min_hcp > total_max_hcp
    should raise ProfileError at construction time.
    """
    with pytest.raises(ProfileError):
        StandardSuitConstraints(
            spades=SuitRange(),
            hearts=SuitRange(),
            diamonds=SuitRange(),
            clubs=SuitRange(),
            total_min_hcp=20,
            total_max_hcp=10,
        )


def test_legacy_dict_with_ns_role_mode_loads_without_error(make_valid_profile) -> None:
    """
    Legacy dicts with ns_role_mode should load without error (field is ignored).
    """
    profile = make_valid_profile()
    raw = profile.to_dict()
    raw["ns_role_mode"] = "north_drives"  # Legacy field — should be tolerated.

    restored = HandProfile.from_dict(raw)
    assert restored.profile_name == profile.profile_name


def test_rotate_default_on_new_profile_is_true(make_valid_profile) -> None:
    """
    New profiles should default rotate_deals_by_default to True.
    (This uses whatever make_valid_profile already returns.)
    """
    profile = make_valid_profile()
    assert getattr(profile, "rotate_deals_by_default", True) is True


def test_rotate_default_round_trip_via_dict(make_valid_profile) -> None:
    """
    rotate_deals_by_default should survive a to_dict / from_dict round-trip.
    """
    profile = make_valid_profile()
    # Flip it to False so we can see the change persist:
    profile.rotate_deals_by_default = False

    data = profile.to_dict()
    assert data["rotate_deals_by_default"] is False

    round_tripped = HandProfile.from_dict(data)
    assert round_tripped.rotate_deals_by_default is False


def test_rotate_default_missing_key_defaults_to_true(make_valid_profile) -> None:
    """
    Old JSON that omits rotate_deals_by_default should still load with True.
    """
    profile = make_valid_profile()
    data = profile.to_dict()

    # Simulate an older JSON file without this field
    data.pop("rotate_deals_by_default", None)

    loaded = HandProfile.from_dict(data)
    # When the key is missing, we expect a default of True
    assert loaded.rotate_deals_by_default is True


# ===================================================================
# SubprofileExclusionClause / SubprofileExclusionData serialization
# ===================================================================


def test_exclusion_clause_round_trip() -> None:
    """SubprofileExclusionClause round-trips through to_dict / from_dict."""
    clause = SubprofileExclusionClause(group="MAJOR", length_eq=5, count=2)
    d = clause.to_dict()
    restored = SubprofileExclusionClause.from_dict(d)
    assert restored == clause
    assert d == {"group": "MAJOR", "length_eq": 5, "count": 2}


def test_exclusion_clause_is_frozen() -> None:
    """SubprofileExclusionClause is frozen (immutable)."""
    clause = SubprofileExclusionClause(group="ANY", length_eq=3, count=1)
    with pytest.raises(AttributeError):
        clause.group = "MINOR"  # type: ignore[misc]


def test_exclusion_data_round_trip_with_shapes() -> None:
    """SubprofileExclusionData with excluded_shapes round-trips."""
    exc = SubprofileExclusionData(
        seat="N",
        subprofile_index=1,
        excluded_shapes=["5332", "4432"],
    )
    d = exc.to_dict()
    restored = SubprofileExclusionData.from_dict(d)
    assert restored.seat == "N"
    assert restored.subprofile_index == 1
    assert restored.excluded_shapes == ["5332", "4432"]
    assert restored.clauses is None


def test_exclusion_data_round_trip_with_clauses() -> None:
    """SubprofileExclusionData with clauses round-trips."""
    exc = SubprofileExclusionData(
        seat="S",
        subprofile_index=2,
        clauses=[
            SubprofileExclusionClause(group="ANY", length_eq=6, count=1),
            SubprofileExclusionClause(group="MINOR", length_eq=4, count=2),
        ],
    )
    d = exc.to_dict()
    restored = SubprofileExclusionData.from_dict(d)
    assert restored.seat == "S"
    assert restored.subprofile_index == 2
    assert restored.excluded_shapes is None
    assert len(restored.clauses) == 2
    assert restored.clauses[0].group == "ANY"
    assert restored.clauses[1].group == "MINOR"


def test_exclusion_data_omits_none_fields() -> None:
    """to_dict() omits excluded_shapes and clauses when they are None."""
    exc = SubprofileExclusionData(seat="E", subprofile_index=1)
    d = exc.to_dict()
    assert "excluded_shapes" not in d
    assert "clauses" not in d
    assert d == {"seat": "E", "subprofile_index": 1}


def test_profile_round_trip_with_exclusions(make_valid_profile) -> None:
    """HandProfile with non-empty exclusions survives to_dict / from_dict."""
    profile = make_valid_profile()
    exclusions = [
        SubprofileExclusionData(
            seat="N",
            subprofile_index=1,
            excluded_shapes=["5332"],
        ),
    ]
    # Build a new profile with exclusions.
    data = profile.to_dict()
    data["subprofile_exclusions"] = [e.to_dict() for e in exclusions]
    loaded = HandProfile.from_dict(data)

    assert len(loaded.subprofile_exclusions) == 1
    assert loaded.subprofile_exclusions[0].seat == "N"
    assert loaded.subprofile_exclusions[0].excluded_shapes == ["5332"]

    # Round-trip again to verify to_dict works on loaded profile.
    data2 = loaded.to_dict()
    loaded2 = HandProfile.from_dict(data2)
    assert len(loaded2.subprofile_exclusions) == 1
    assert loaded2.subprofile_exclusions[0].seat == "N"


def test_exclusion_validate_catches_bad_subprofile_index(make_valid_profile) -> None:
    """validate() correctly checks subprofile_index against seat's subprofile count."""
    profile = make_valid_profile()
    # Index 99 should be out of range (each seat has 1 subprofile).
    exc = SubprofileExclusionData(
        seat="N",
        subprofile_index=99,
        excluded_shapes=["5332"],
    )
    with pytest.raises(ProfileError, match="Invalid subprofile index"):
        exc.validate(profile)


# ---------------------------------------------------------------------------
# Wildcard "x" support in excluded_shapes
# ---------------------------------------------------------------------------


def test_exclusion_wildcard_shape_accepted(make_valid_profile) -> None:
    """Validation accepts wildcard shapes like '64xx' and 'x4xx'."""
    profile = make_valid_profile()
    exc1 = SubprofileExclusionData(seat="N", subprofile_index=1, excluded_shapes=["64xx"])
    exc1.validate(profile)  # should not raise
    exc2 = SubprofileExclusionData(seat="N", subprofile_index=1, excluded_shapes=["x4xx"])
    exc2.validate(profile)  # should not raise


def test_exclusion_wildcard_digits_exceed_13_rejected(make_valid_profile) -> None:
    """Validation rejects wildcard shapes where specified digits exceed 13."""
    profile = make_valid_profile()
    exc = SubprofileExclusionData(seat="N", subprofile_index=1, excluded_shapes=["99xx"])
    with pytest.raises(ProfileError, match="Specified digits exceed 13"):
        exc.validate(profile)


def test_exclusion_wildcard_round_trip() -> None:
    """Wildcard shapes survive to_dict → from_dict round-trip."""
    exc = SubprofileExclusionData(seat="N", subprofile_index=1, excluded_shapes=["64xx", "5xxx"])
    d = exc.to_dict()
    restored = SubprofileExclusionData.from_dict(d)
    assert restored.excluded_shapes == ["64xx", "5xxx"]


def test_exclusion_exact_shape_still_validated(make_valid_profile) -> None:
    """Exact shapes (no wildcards) still enforce sum-to-13."""
    profile = make_valid_profile()
    exc = SubprofileExclusionData(seat="N", subprofile_index=1, excluded_shapes=["9999"])
    with pytest.raises(ProfileError, match="Shape does not sum to 13"):
        exc.validate(profile)


# ---------------------------------------------------------------------------
# SubProfile name field + sub_label helper
# ---------------------------------------------------------------------------


def test_subprofile_name_round_trip() -> None:
    """SubProfile.name survives to_dict → from_dict."""
    sub = SubProfile(standard=_standard_all_open(), name="Strong opener")
    d = sub.to_dict()
    assert d["name"] == "Strong opener"
    restored = SubProfile.from_dict(d)
    assert restored.name == "Strong opener"


def test_subprofile_name_none_omitted() -> None:
    """When name is None, to_dict() should not include a 'name' key."""
    sub = SubProfile(standard=_standard_all_open())
    d = sub.to_dict()
    assert "name" not in d


def test_subprofile_name_missing_defaults_none() -> None:
    """Backwards compat: from_dict with no 'name' key produces name=None."""
    d = SubProfile(standard=_standard_all_open()).to_dict()
    assert "name" not in d
    restored = SubProfile.from_dict(d)
    assert restored.name is None


def test_subprofile_name_empty_treated_as_none() -> None:
    """Blank/whitespace-only name is normalised to None on load."""
    d = SubProfile(standard=_standard_all_open()).to_dict()
    d["name"] = "   "
    restored = SubProfile.from_dict(d)
    assert restored.name is None


def test_sub_label_with_name() -> None:
    """sub_label includes the name in parentheses when set."""
    sub = SubProfile(standard=_standard_all_open(), name="Weak response")
    assert sub_label(1, sub) == "Sub-profile 1 (Weak response)"


def test_sub_label_without_name() -> None:
    """sub_label shows only the index when name is None."""
    sub = SubProfile(standard=_standard_all_open())
    assert sub_label(2, sub) == "Sub-profile 2"


# ===================================================================
# EW role mode / usage
# ===================================================================


def test_legacy_ew_role_mode_tolerated(make_valid_profile) -> None:
    """Legacy JSON with ew_role_mode loads without error (field ignored)."""
    profile = make_valid_profile()
    raw = profile.to_dict()
    raw["ew_role_mode"] = "east_drives"
    restored = HandProfile.from_dict(raw)
    assert restored.profile_name == profile.profile_name
