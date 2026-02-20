"""
Tests for profile_diagnostic.py helper functions and the main runner.

Covers:
  - _hand_hcp() — HCP sum for a hand
  - _suit_count() — cards in a suit
  - _hand_shape() — shape string (S-H-D-C)
  - _fmt_row() — failure attribution table row formatting
  - run_profile_diagnostic() — main diagnostic runner (smoke test)
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Dict, List

import pytest

from bridge_engine.profile_diagnostic import (
    _hand_hcp,
    _suit_count,
    _hand_shape,
    _fmt_row,
    run_profile_diagnostic,
)


# ===================================================================
# _hand_hcp
# ===================================================================


class TestHandHcp:
    """Tests for _hand_hcp."""

    def test_all_aces(self):
        """4 aces = 16 HCP."""
        hand = ["AS", "AH", "AD", "AC"]
        assert _hand_hcp(hand) == 16

    def test_no_honours(self):
        """Hand of spot cards = 0 HCP."""
        hand = ["2S", "3S", "4S", "5S", "6S", "7S", "8S", "9S", "TS", "2H", "3H", "4H", "5H"]
        assert _hand_hcp(hand) == 0

    def test_mixed_hand(self):
        """A=4, K=3, Q=2, J=1 = 10 HCP."""
        hand = ["AS", "KH", "QD", "JC", "2S", "3S", "4S", "5S", "6S", "7S", "8S", "9S", "TS"]
        assert _hand_hcp(hand) == 10

    def test_empty_hand(self):
        """Empty hand = 0 HCP."""
        assert _hand_hcp([]) == 0


# ===================================================================
# _suit_count
# ===================================================================


class TestSuitCount:
    """Tests for _suit_count."""

    def test_count_spades(self):
        """Count spades in a mixed hand."""
        hand = ["AS", "KS", "QS", "2H", "3D", "4C"]
        assert _suit_count(hand, "S") == 3

    def test_count_zero(self):
        """No cards of the suit = 0."""
        hand = ["2H", "3H", "4D"]
        assert _suit_count(hand, "S") == 0

    def test_all_one_suit(self):
        """All 13 cards in one suit."""
        hand = [f"{r}S" for r in "AKQJT98765432"]
        assert _suit_count(hand, "S") == 13


# ===================================================================
# _hand_shape
# ===================================================================


class TestHandShape:
    """Tests for _hand_shape."""

    def test_balanced(self):
        """4-3-3-3 shape."""
        hand = ["AS", "KS", "QS", "JS", "2H", "3H", "4H", "5D", "6D", "7D", "8C", "9C", "TC"]
        assert _hand_shape(hand) == "4-3-3-3"

    def test_long_suit(self):
        """7-3-2-1 shape."""
        hand = ["AS", "KS", "QS", "JS", "TS", "9S", "8S", "2H", "3H", "4H", "5D", "6D", "7C"]
        assert _hand_shape(hand) == "7-3-2-1"

    def test_void(self):
        """5-4-4-0 shape (void in clubs)."""
        hand = ["AS", "KS", "QS", "JS", "TS", "2H", "3H", "4H", "5H", "6D", "7D", "8D", "9D"]
        assert _hand_shape(hand) == "5-4-4-0"


# ===================================================================
# _fmt_row
# ===================================================================


class TestFmtRow:
    """Tests for _fmt_row."""

    def test_basic_format(self):
        """Row includes label, per-seat counts with percentages, and total."""
        counts: Dict[str, int] = {"W": 10, "N": 20, "S": 30, "E": 40}
        row = _fmt_row("test_label", counts)
        assert "test_label" in row
        assert "10" in row
        assert "20" in row
        assert "30" in row
        assert "40" in row
        assert "100" in row  # total

    def test_zero_total(self):
        """All zeros: percentages should be 0.0%."""
        counts: Dict[str, int] = {"W": 0, "N": 0, "S": 0, "E": 0}
        row = _fmt_row("zeros", counts)
        assert "0.0%" in row

    def test_seats_in_wnes_order(self):
        """Seats appear in W, N, S, E order (matching diagnostic output)."""
        counts: Dict[str, int] = {"W": 1, "N": 2, "S": 3, "E": 4}
        row = _fmt_row("order_test", counts)
        # W count appears before N count in the string
        w_pos = row.index("1 (")
        n_pos = row.index("2 (")
        assert w_pos < n_pos


# ===================================================================
# run_profile_diagnostic — smoke test
# ===================================================================


class TestRunProfileDiagnostic:
    """Smoke test for run_profile_diagnostic with a real profile."""

    def test_diagnostic_runs_without_error(self, capsys):
        """Diagnostic completes on a simple profile and prints output."""
        from bridge_engine.hand_profile import HandProfile

        # Build a minimal unconstrained profile
        profile = HandProfile.from_dict(
            {
                "profile_name": "Diagnostic Test",
                "description": "Test profile for diagnostic",
                "tag": "Opener",
                "dealer": "N",
                "hand_dealing_order": ["N", "E", "S", "W"],
                "seat_profiles": {},
                "schema_version": 1,
            }
        )

        # Run with just 2 boards for speed
        run_profile_diagnostic(profile, num_boards=2, seed_base=99999)

        captured = capsys.readouterr()
        assert "Profile Diagnostic" in captured.out
        assert "SUMMARY" in captured.out
        assert "2/2 boards succeeded" in captured.out
