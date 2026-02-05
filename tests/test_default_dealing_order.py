# tests/test_default_dealing_order.py
"""
Tests for default dealing order generation (dealer + clockwise).
"""

from bridge_engine.hand_profile_model import _default_dealing_order, HandProfile


# ---------------------------------------------------------------------------
# Unit tests for _default_dealing_order()
# ---------------------------------------------------------------------------

def test_default_dealing_order_north():
    """Dealer N → N, E, S, W (clockwise from North)."""
    assert _default_dealing_order("N") == ["N", "E", "S", "W"]


def test_default_dealing_order_east():
    """Dealer E → E, S, W, N (clockwise from East)."""
    assert _default_dealing_order("E") == ["E", "S", "W", "N"]


def test_default_dealing_order_south():
    """Dealer S → S, W, N, E (clockwise from South)."""
    assert _default_dealing_order("S") == ["S", "W", "N", "E"]


def test_default_dealing_order_west():
    """Dealer W → W, N, E, S (clockwise from West)."""
    assert _default_dealing_order("W") == ["W", "N", "E", "S"]


# ---------------------------------------------------------------------------
# Integration tests for HandProfile.from_dict() with missing dealing order
# ---------------------------------------------------------------------------

def _minimal_profile_dict(dealer: str, include_dealing_order: bool = True):
    """Create a minimal valid profile dict for testing."""
    d = {
        "profile_name": "Test Profile",
        "description": "Test",
        "dealer": dealer,
        "tag": "Opener",
        "seat_profiles": {},
    }
    if include_dealing_order:
        d["hand_dealing_order"] = _default_dealing_order(dealer)
    return d


def test_from_dict_uses_provided_dealing_order():
    """When hand_dealing_order is provided, use it."""
    data = _minimal_profile_dict("N", include_dealing_order=False)
    data["hand_dealing_order"] = ["N", "S", "E", "W"]  # Custom order

    profile = HandProfile.from_dict(data)

    assert profile.hand_dealing_order == ["N", "S", "E", "W"]


def test_from_dict_generates_default_when_missing_north():
    """When hand_dealing_order is missing, generate default for dealer N."""
    data = _minimal_profile_dict("N", include_dealing_order=False)

    profile = HandProfile.from_dict(data)

    assert profile.hand_dealing_order == ["N", "E", "S", "W"]


def test_from_dict_generates_default_when_missing_east():
    """When hand_dealing_order is missing, generate default for dealer E."""
    data = _minimal_profile_dict("E", include_dealing_order=False)

    profile = HandProfile.from_dict(data)

    assert profile.hand_dealing_order == ["E", "S", "W", "N"]


def test_from_dict_generates_default_when_missing_south():
    """When hand_dealing_order is missing, generate default for dealer S."""
    data = _minimal_profile_dict("S", include_dealing_order=False)

    profile = HandProfile.from_dict(data)

    assert profile.hand_dealing_order == ["S", "W", "N", "E"]


def test_from_dict_generates_default_when_missing_west():
    """When hand_dealing_order is missing, generate default for dealer W."""
    data = _minimal_profile_dict("W", include_dealing_order=False)

    profile = HandProfile.from_dict(data)

    assert profile.hand_dealing_order == ["W", "N", "E", "S"]
