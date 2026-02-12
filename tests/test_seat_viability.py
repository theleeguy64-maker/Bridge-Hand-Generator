# tests/test_seat_viability.py

from bridge_engine.seat_viability import validate_profile_viability_light


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