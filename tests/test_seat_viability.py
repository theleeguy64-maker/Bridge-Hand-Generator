# tests/test_seat_viability.py

import pytest

from bridge_engine.seat_viability import (
    _shape_matches_pattern,
    validate_profile_viability_light,
)


def test_validate_profile_viability_light_accepts_make_valid_profile(
    make_valid_profile,
) -> None:
    """
    Integration-ish smoke test:

    The known-good "Test profile" produced by make_valid_profile (used by the
    deal invariants tests) should also be accepted by the light seat-viability
    check. This ties the invariants profile into the seat-viability pipeline.
    """
    profile = make_valid_profile()

    # Should not raise.
    validate_profile_viability_light(profile)


# ---------------------------------------------------------------------------
# _shape_matches_pattern — wildcard "x" matching
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "shape, pattern, expected",
    [
        ("6430", "64xx", True),  # wildcard matches any minor distribution
        ("6421", "64xx", True),  # different minor distribution still matches
        ("4630", "64xx", False),  # order matters — S/H/D/C positions
        ("4333", "4333", True),  # exact match still works
        ("4333", "4334", False),  # exact mismatch
        ("5431", "5xxx", True),  # single specified digit + wildcards
        ("3541", "x5xx", True),  # wildcard in first position
        ("3541", "x5x2", False),  # partial wildcard mismatch
        ("0004", "000x", True),  # edge case: 0s with wildcard
        ("xxxx", "xxxx", True),  # all wildcards (pattern matches literal 'x' in shape — academic)
    ],
)
def test_shape_matches_pattern(shape: str, pattern: str, expected: bool) -> None:
    """_shape_matches_pattern handles exact and wildcard patterns correctly."""
    assert _shape_matches_pattern(shape, pattern) is expected
