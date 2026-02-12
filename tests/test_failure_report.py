"""
Tests for bridge_engine/failure_report.py

Tests the failure attribution report collection and export functionality.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bridge_engine.failure_report import (
    FailureAttributionReport,
    collect_failure_attribution,
)


# ---------------------------------------------------------------------------
# Tests for FailureAttributionReport
# ---------------------------------------------------------------------------

class TestFailureAttributionReport:
    """Tests for FailureAttributionReport dataclass."""

    def test_success_rate_calculation(self) -> None:
        """Success rate should be succeeded / requested."""
        report = FailureAttributionReport(
            profile_name="Test",
            num_boards_requested=100,
            num_boards_succeeded=80,
            num_boards_failed=20,
            total_attempts=500,
        )
        assert report.success_rate == 0.8

    def test_success_rate_zero_boards(self) -> None:
        """Success rate should be 0.0 when no boards requested."""
        report = FailureAttributionReport(
            profile_name="Test",
            num_boards_requested=0,
            num_boards_succeeded=0,
            num_boards_failed=0,
            total_attempts=0,
        )
        assert report.success_rate == 0.0

    def test_pain_share_calculation(self) -> None:
        """Pain share should be proportion of failures per seat."""
        report = FailureAttributionReport(
            profile_name="Test",
            num_boards_requested=100,
            num_boards_succeeded=50,
            num_boards_failed=50,
            total_attempts=500,
            seat_fail_as_seat={"N": 40, "E": 10, "S": 40, "W": 10},
        )
        ps = report.pain_share
        assert ps["N"] == 0.4
        assert ps["E"] == 0.1
        assert ps["S"] == 0.4
        assert ps["W"] == 0.1

    def test_pain_share_no_failures(self) -> None:
        """Pain share should be all zeros when no failures."""
        report = FailureAttributionReport(
            profile_name="Test",
            num_boards_requested=100,
            num_boards_succeeded=100,
            num_boards_failed=0,
            total_attempts=100,
        )
        ps = report.pain_share
        assert all(v == 0.0 for v in ps.values())

    def test_hardest_seat(self) -> None:
        """Hardest seat should be the one with highest pain share."""
        report = FailureAttributionReport(
            profile_name="Test",
            num_boards_requested=100,
            num_boards_succeeded=50,
            num_boards_failed=50,
            total_attempts=500,
            seat_fail_as_seat={"N": 50, "E": 10, "S": 30, "W": 10},
        )
        assert report.hardest_seat == "N"

    def test_hardest_seat_none_when_no_failures(self) -> None:
        """Hardest seat should be None when no failures."""
        report = FailureAttributionReport(
            profile_name="Test",
            num_boards_requested=100,
            num_boards_succeeded=100,
            num_boards_failed=0,
            total_attempts=100,
        )
        assert report.hardest_seat is None

    def test_to_dict(self) -> None:
        """to_dict should include all fields and computed properties."""
        report = FailureAttributionReport(
            profile_name="TestProfile",
            num_boards_requested=100,
            num_boards_succeeded=80,
            num_boards_failed=20,
            total_attempts=500,
        )
        d = report.to_dict()

        assert d["profile_name"] == "TestProfile"
        assert d["num_boards_requested"] == 100
        assert d["success_rate"] == 0.8
        assert "pain_share" in d
        assert "hardest_seat" in d

    def test_to_json(self, tmp_path: Path) -> None:
        """to_json should write valid JSON file."""
        report = FailureAttributionReport(
            profile_name="TestProfile",
            num_boards_requested=100,
            num_boards_succeeded=80,
            num_boards_failed=20,
            total_attempts=500,
        )
        json_path = tmp_path / "report.json"
        report.to_json(json_path)

        # Verify file exists and is valid JSON
        assert json_path.exists()
        data = json.loads(json_path.read_text())
        assert data["profile_name"] == "TestProfile"
        assert data["success_rate"] == 0.8

    def test_to_csv(self, tmp_path: Path) -> None:
        """to_csv should write valid CSV file."""
        report = FailureAttributionReport(
            profile_name="TestProfile",
            num_boards_requested=100,
            num_boards_succeeded=80,
            num_boards_failed=20,
            total_attempts=500,
            seat_fail_as_seat={"N": 40, "E": 10, "S": 30, "W": 20},
        )
        csv_path = tmp_path / "report.csv"
        report.to_csv(csv_path)

        # Verify file exists and has correct structure
        assert csv_path.exists()
        lines = csv_path.read_text().strip().split("\n")
        assert len(lines) == 5  # Header + 4 seats
        assert "seat" in lines[0]
        assert "fail_as_seat" in lines[0]
        assert "pain_share" in lines[0]

    def test_summary(self) -> None:
        """summary should return human-readable string."""
        report = FailureAttributionReport(
            profile_name="TestProfile",
            num_boards_requested=100,
            num_boards_succeeded=80,
            num_boards_failed=20,
            total_attempts=500,
        )
        summary = report.summary()

        assert "TestProfile" in summary
        assert "80/100" in summary
        assert "80.0%" in summary


# ---------------------------------------------------------------------------
# Tests for collect_failure_attribution
# ---------------------------------------------------------------------------

class TestCollectFailureAttribution:
    """Tests for collect_failure_attribution() function."""

    def test_collects_data_from_profile(self, make_valid_profile) -> None:
        """Should collect attribution data from deal generation."""
        profile = make_valid_profile()
        report = collect_failure_attribution(
            profile=profile,
            num_boards=10,
            seed=42,
            max_attempts=100,
        )

        assert report.profile_name == profile.profile_name
        assert report.num_boards_requested == 10
        # With a valid profile and reasonable attempts, most should succeed
        assert report.num_boards_succeeded >= 0
        assert report.num_boards_failed >= 0
        assert report.num_boards_succeeded + report.num_boards_failed == 10

    def test_reproducible_with_seed(self, make_valid_profile) -> None:
        """Same seed should produce same results."""
        profile = make_valid_profile()

        report1 = collect_failure_attribution(profile, num_boards=5, seed=123)
        report2 = collect_failure_attribution(profile, num_boards=5, seed=123)

        assert report1.num_boards_succeeded == report2.num_boards_succeeded
        assert report1.seat_fail_as_seat == report2.seat_fail_as_seat

    def test_different_seeds_may_differ(self, make_valid_profile) -> None:
        """Different seeds may produce different results."""
        profile = make_valid_profile()

        report1 = collect_failure_attribution(profile, num_boards=20, seed=1)
        report2 = collect_failure_attribution(profile, num_boards=20, seed=9999)

        # With enough boards, there's likely to be some difference
        # (but this isn't guaranteed, so we just check the reports are valid)
        assert report1.num_boards_requested == 20
        assert report2.num_boards_requested == 20
