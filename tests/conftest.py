from __future__ import annotations

import pytest
import copy

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
                    partner_contingent_constraint=PartnerContingentData(
                        partner_seat="E", suit_range=SuitRange()
                    ),
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

        # Convert JSON → HandProfile
        return HandProfile.from_dict(data)

    return _make