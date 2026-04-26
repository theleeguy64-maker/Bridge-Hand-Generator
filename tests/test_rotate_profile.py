"""Tests for bridge_engine.rotate_profile."""

from __future__ import annotations

import pytest

from bridge_engine.rotate_profile import ROTATE_MAP, _rotate_seat


def test_rotate_seat_map():
    assert ROTATE_MAP == {"W": "N", "N": "E", "E": "S", "S": "W"}
    assert _rotate_seat("W") == "N"
    assert _rotate_seat("N") == "E"
    assert _rotate_seat("E") == "S"
    assert _rotate_seat("S") == "W"


def test_rotate_seat_rejects_bad_input():
    with pytest.raises(ValueError):
        _rotate_seat("X")
    with pytest.raises(ValueError):
        _rotate_seat("")
