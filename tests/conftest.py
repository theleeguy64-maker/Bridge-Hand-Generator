from __future__ import annotations

import copy
from typing import Any

import pytest

from bridge_engine.hand_profile import (
    HandProfile,
    SuitRange,
    StandardSuitConstraints,
    RandomSuitConstraintData,
    PartnerContingentData,
    SubProfile,
    SeatProfile,
)


# ---------------------------------------------------------------------------
# Minimal valid profile template for fixture
# ---------------------------------------------------------------------------

# Construct a reusable minimal valid JSON-like dict structure.
# This mimics a realistic HandProfile.to_dict() output.
MINIMAL_VALID_PROFILE = {
    "profile_name": "ValidProfile",
    "description": "Minimal valid profile",
    "dealer": "E",
    "hand_dealing_order": ["E", "S", "W", "N"],
    "tag": "Overcaller",
    "author": "",
    "version": "0.1",
    "seat_profiles": {
        # These are filled in dynamically to ensure no tight coupling.
        # The fixture will overwrite these with fully-formed SeatProfile dicts.
    },
    # The new field under test; defaults to True if missing.
    "rotate_deals_by_default": True,
}


def _standard_all_open() -> StandardSuitConstraints:
    """Return completely open suit constraints."""
    r = SuitRange()
    return StandardSuitConstraints(spades=r, hearts=r, diamonds=r, clubs=r)


@pytest.fixture
def make_valid_profile():
    """
    Factory returning a structurally valid HandProfile instance.

    Uses a JSON-style dict → HandProfile.from_dict so tests don't depend
    on HandProfile.__init__ signature.
    """

    def _make(profile_name: str = "Test profile", version: str = "0.1") -> HandProfile:
        data = copy.deepcopy(MINIMAL_VALID_PROFILE)

        data["profile_name"] = profile_name
        data["version"] = version

        # Build seat profiles dynamically
        rs = RandomSuitConstraintData(
            required_suits_count=1,
            allowed_suits=["S"],
            suit_ranges=[SuitRange()],
        )

        north = SeatProfile(seat="N", subprofiles=[SubProfile(_standard_all_open())])
        east = SeatProfile(
            seat="E",
            subprofiles=[SubProfile(_standard_all_open(), random_suit_constraint=rs)],
        )
        south = SeatProfile(seat="S", subprofiles=[SubProfile(_standard_all_open())])
        west = SeatProfile(
            seat="W",
            subprofiles=[
                SubProfile(
                    standard=_standard_all_open(),
                    partner_contingent_constraint=PartnerContingentData(partner_seat="E", suit_range=SuitRange()),
                )
            ],
        )

        # Serialize seat profiles into dict form
        data["seat_profiles"] = {
            "N": north.to_dict(),
            "E": east.to_dict(),
            "S": south.to_dict(),
            "W": west.to_dict(),
        }

        # Ensure rotate flag is present (default to True)
        data.setdefault("rotate_deals_by_default", True)

        # P1.1 refactor: explicitly set invariants safety flag for test profiles
        # (was previously set via magic string check on "Test profile" name)
        data["is_invariants_safety_profile"] = True

        # Convert JSON → HandProfile
        return HandProfile.from_dict(data)

    return _make


def _canonical_profile_dict() -> dict[str, Any]:
    """A canonical HandProfile-shaped dict exercising every field touched
    by the rotation rules. Deep-copy via the fixture before mutating."""
    return {
        "profile_name": "Opps Open 1NT and we Overcall",
        "description": "Opps open 1NT, we overcall",
        "category": "We Compete",
        "author": "Lee",
        "tag": "Overcaller",
        "version": "1.0",
        "schema_version": 1,
        "sort_order": 5,
        "dealer": "W",
        "hand_dealing_order": ["W", "N", "E", "S"],
        "rotate_deals_by_default": True,
        "is_invariants_safety_profile": False,
        "subprofile_exclusions": [
            {"seat": "W", "subprofile_index": 1},
            {"seat": "E", "subprofile_index": 2},
        ],
        "ns_linked_profile": {
            "primary_seat": "N",
            "subprofile_map": {"1": [1], "2": [1, 2]},
        },
        "ew_linked_profile": {
            "primary_seat": "E",
            "subprofile_map": {"1": [1]},
        },
        "seat_profiles": {
            seat: {
                "seat": seat,
                "subprofiles": [
                    {
                        "name": "Balanced",
                        "weight_percent": 100.0,
                        "standard": {
                            "clubs": {"min_cards": 0, "max_cards": 5, "min_hcp": 0, "max_hcp": 8},
                            "diamonds": {"min_cards": 0, "max_cards": 5, "min_hcp": 0, "max_hcp": 8},
                            "hearts": {"min_cards": 0, "max_cards": 5, "min_hcp": 0, "max_hcp": 8},
                            "spades": {"min_cards": 0, "max_cards": 5, "min_hcp": 0, "max_hcp": 8},
                            "total_min_hcp": 6,
                            "total_max_hcp": 10,
                        },
                        "random_suit_constraint": None,
                        "partner_contingent_constraint": (
                            {
                                "partner_seat": "S",
                                "use_non_chosen_suit": False,
                                "suit_range": {"min_cards": 4, "max_cards": 6, "min_hcp": 0, "max_hcp": 7},
                            }
                            if seat == "N"
                            else None
                        ),
                        "opponents_contingent_suit_constraint": (
                            {
                                "opponent_seat": "W",
                                "use_non_chosen_suit": True,
                                "suit_range": {"min_cards": 0, "max_cards": 3, "min_hcp": 0, "max_hcp": 8},
                            }
                            if seat == "E"
                            else None
                        ),
                    }
                ],
            }
            for seat in ("N", "E", "S", "W")
        },
    }


@pytest.fixture
def make_profile_dict():
    """Return a factory that produces a fresh deep copy on each call."""

    def _factory() -> dict[str, Any]:
        return copy.deepcopy(_canonical_profile_dict())

    return _factory
