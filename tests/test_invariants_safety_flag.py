from bridge_engine.hand_profile_model import HandProfile
from bridge_engine.seat_viability import validate_profile_viability_light

from tests.test_deal_generator_section_c import (  # type: ignore
    _random_suit_w_partner_contingent_e_profile,
)


def test_test_profile_is_invariants_safety_profile(make_valid_profile) -> None:
    """
    The simple 'Test profile' used by deal invariants should explicitly
    opt into the unconstrained fallback path via is_invariants_safety_profile.
    """
    # make_valid_profile is a pytest fixture (from conftest), injected by name
    profile = make_valid_profile()
    assert isinstance(profile, HandProfile)

    # Sanity: profile must be viability-light OK.
    validate_profile_viability_light(profile)

    assert getattr(profile, "is_invariants_safety_profile", False) is True


def test_random_suit_w_pc_e_is_not_invariants_safety_profile() -> None:
    """
    The Random Suit W + Partner Contingent E profile should NOT be marked as
    an invariants safety profile — we want its constraints to be enforced.
    """
    profile = _random_suit_w_partner_contingent_e_profile()
    assert isinstance(profile, HandProfile)

    assert getattr(profile, "is_invariants_safety_profile", False) is False
