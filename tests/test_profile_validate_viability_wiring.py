import pytest

from bridge_engine import hand_profile_validate


class _DummyProfile:
    """Minimal stand-in for a HandProfile instance used inside validate_profile."""
    def __init__(self) -> None:
        # validate_profile may iterate subprofile_exclusions, so make it harmless
        self.subprofile_exclusions = []


def _install_common_patches(monkeypatch, dummy_profile):
    """
    Patch validate_profile(...) internals so we control the flow and
    don't depend on real HandProfile / structural validation logic.
    """

    # 1) Replace HandProfile with a dummy class whose from_dict returns our dummy_profile.
    class DummyHandProfile:
        @classmethod
        def from_dict(cls, raw):
            # raw is whatever _normalise_profile_input(...) returned; we don't care.
            return dummy_profile

    monkeypatch.setattr(hand_profile_validate, "HandProfile", DummyHandProfile)

    # 2) Make the earlier structural validators no-ops so they
    #    don't complain about our dummy profile.
    monkeypatch.setattr(
        hand_profile_validate,
        "_validate_partner_contingent",
        lambda profile: None,
    )
    monkeypatch.setattr(
        hand_profile_validate,
        "_validate_opponent_contingent",
        lambda profile: None,
    )
    monkeypatch.setattr(
        hand_profile_validate,
        "_validate_ns_role_usage_coverage",
        lambda profile: None,
    )
    monkeypatch.setattr(
        hand_profile_validate,
        "_validate_random_suit_vs_standard",
        lambda profile: None,
    )


def test_validate_profile_calls_viability(monkeypatch) -> None:
    """
    validate_profile(...) should invoke validate_profile_viability(...)
    as part of its pipeline.  (Step 9 calls the extended viability check
    which internally calls light + NS coupling + cross-seat checks.)
    """
    dummy_profile = _DummyProfile()
    _install_common_patches(monkeypatch, dummy_profile)

    call_counter = {"count": 0}

    def fake_viability(profile):
        call_counter["count"] += 1
        # Ensure we're being passed the HandProfile instance built inside validate_profile
        assert profile is dummy_profile

    monkeypatch.setattr(
        hand_profile_validate,
        "validate_profile_viability",
        fake_viability,
    )

    # Input value is irrelevant; we fully control the internals via monkeypatch.
    hand_profile_validate.validate_profile({"anything": "goes"})

    assert call_counter["count"] == 1


def test_validate_profile_propagates_viability_errors(monkeypatch) -> None:
    """
    If validate_profile_viability(...) raises, validate_profile(...)
    must surface that error to the caller (not swallow it).
    """
    dummy_profile = _DummyProfile()
    _install_common_patches(monkeypatch, dummy_profile)

    class SentinelError(Exception):
        pass

    def fake_viability(profile):
        raise SentinelError("boom")

    monkeypatch.setattr(
        hand_profile_validate,
        "validate_profile_viability",
        fake_viability,
    )

    with pytest.raises(SentinelError):
        hand_profile_validate.validate_profile({"anything": "goes"})