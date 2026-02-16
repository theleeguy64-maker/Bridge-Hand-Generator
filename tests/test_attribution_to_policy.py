# tests/test_attribution_to_policy.py
"""
Tests for TODO Item 2: Connect HCP/shape failure attribution to helper policy.

The _is_shape_dominant_failure() function decides whether constructive help
is appropriate based on the HCP vs shape failure ratio:
- Shape-dominant failures → constructive CAN help (pre-commit card counts)
- HCP-dominant failures → constructive WON'T help (can't pre-commit HCP)
"""

from bridge_engine.deal_generator import _is_shape_dominant_failure


# ---------------------------------------------------------------------------
# Unit tests for _is_shape_dominant_failure()
# ---------------------------------------------------------------------------


def test_is_shape_dominant_no_data_returns_true():
    """When no failures recorded, return True (benefit of the doubt)."""
    result = _is_shape_dominant_failure(
        seat="N",
        seat_fail_hcp={},
        seat_fail_shape={},
        min_shape_ratio=0.5,
    )
    assert result is True


def test_is_shape_dominant_all_shape_fails_returns_true():
    """100% shape failures → definitely shape-dominant → True."""
    result = _is_shape_dominant_failure(
        seat="N",
        seat_fail_hcp={"N": 0},
        seat_fail_shape={"N": 10},
        min_shape_ratio=0.5,
    )
    assert result is True


def test_is_shape_dominant_all_hcp_fails_returns_false():
    """100% HCP failures → definitely HCP-dominant → False."""
    result = _is_shape_dominant_failure(
        seat="N",
        seat_fail_hcp={"N": 10},
        seat_fail_shape={"N": 0},
        min_shape_ratio=0.5,
    )
    assert result is False


def test_is_shape_dominant_at_threshold_returns_true():
    """Exactly at threshold (50%) → shape-dominant → True."""
    # 5 shape, 5 hcp → ratio = 0.5 → exactly at threshold
    result = _is_shape_dominant_failure(
        seat="N",
        seat_fail_hcp={"N": 5},
        seat_fail_shape={"N": 5},
        min_shape_ratio=0.5,
    )
    assert result is True


def test_is_shape_dominant_below_threshold_returns_false():
    """Below threshold (49% shape) → HCP-dominant → False."""
    # 49 shape, 51 hcp → ratio = 0.49 → below 0.5 threshold
    result = _is_shape_dominant_failure(
        seat="N",
        seat_fail_hcp={"N": 51},
        seat_fail_shape={"N": 49},
        min_shape_ratio=0.5,
    )
    assert result is False


def test_is_shape_dominant_seat_not_in_counters_returns_true():
    """Seat not present in counters → no data → benefit of doubt → True."""
    result = _is_shape_dominant_failure(
        seat="N",
        seat_fail_hcp={"S": 10},  # Different seat
        seat_fail_shape={"S": 5},
        min_shape_ratio=0.5,
    )
    assert result is True


def test_is_shape_dominant_custom_threshold():
    """Test with a stricter threshold (0.7)."""
    # 60% shape → below 0.7 threshold → False
    result = _is_shape_dominant_failure(
        seat="N",
        seat_fail_hcp={"N": 40},
        seat_fail_shape={"N": 60},
        min_shape_ratio=0.7,
    )
    assert result is False

    # 70% shape → at threshold → True
    result = _is_shape_dominant_failure(
        seat="N",
        seat_fail_hcp={"N": 30},
        seat_fail_shape={"N": 70},
        min_shape_ratio=0.7,
    )
    assert result is True


def test_is_shape_dominant_disabled_with_zero_threshold():
    """When threshold is 0.0, even 100% HCP failures return True."""
    result = _is_shape_dominant_failure(
        seat="N",
        seat_fail_hcp={"N": 100},
        seat_fail_shape={"N": 0},
        min_shape_ratio=0.0,  # Disabled - always allow constructive
    )
    assert result is True
