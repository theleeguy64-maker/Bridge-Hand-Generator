import pytest

from bridge_engine import seat_viability


def test_validate_profile_viability_calls_light(monkeypatch) -> None:
    """
    validate_profile_viability(...) should delegate to
    validate_profile_viability_light(...), passing through the profile.
    """
    calls = {"count": 0}
    sentinel_profile = object()

    def fake_light(profile) -> None:
        calls["count"] += 1
        # Ensure the same object is passed through
        assert profile is sentinel_profile

    monkeypatch.setattr(
        seat_viability,
        "validate_profile_viability_light",
        fake_light,
    )

    seat_viability.validate_profile_viability(sentinel_profile)

    assert calls["count"] == 1


def test_validate_profile_viability_propagates_errors(monkeypatch) -> None:
    """
    If validate_profile_viability_light(...) raises, the wrapper should
    surface that error to the caller (not swallow it).
    """
    class SentinelError(Exception):
        pass

    def fake_light(profile) -> None:
        raise SentinelError("boom")

    monkeypatch.setattr(
        seat_viability,
        "validate_profile_viability_light",
        fake_light,
    )

    with pytest.raises(SentinelError):
        seat_viability.validate_profile_viability(object())