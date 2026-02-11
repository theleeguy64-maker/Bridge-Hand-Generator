"""
Failure Attribution Report Module

Provides structured export of failure attribution data from deal generation.
Useful for analyzing where deal generation fails (which seats, HCP vs shape).

Usage:
    from bridge_engine.failure_report import collect_failure_attribution

    report = collect_failure_attribution(profile, num_boards=100)
    report.to_json(Path("report.json"))
    report.to_csv(Path("report.csv"))
"""

from __future__ import annotations

import csv
import json
import random
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, Optional

from .hand_profile_model import HandProfile
from . import deal_generator as dg


Seat = str  # "N", "E", "S", "W"


@dataclass
class FailureAttributionReport:
    """
    Structured failure attribution data for export.

    Collects per-seat failure counts and computes derived metrics.
    """

    # Profile metadata
    profile_name: str
    num_boards_requested: int
    num_boards_succeeded: int
    num_boards_failed: int
    total_attempts: int

    # Per-seat failure counters (aggregated across all attempts)
    seat_fail_as_seat: Dict[Seat, int] = field(default_factory=dict)
    seat_fail_global_other: Dict[Seat, int] = field(default_factory=dict)
    seat_fail_global_unchecked: Dict[Seat, int] = field(default_factory=dict)
    seat_fail_hcp: Dict[Seat, int] = field(default_factory=dict)
    seat_fail_shape: Dict[Seat, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Initialize empty dicts for any missing seats."""
        for seat in ("N", "E", "S", "W"):
            self.seat_fail_as_seat.setdefault(seat, 0)
            self.seat_fail_global_other.setdefault(seat, 0)
            self.seat_fail_global_unchecked.setdefault(seat, 0)
            self.seat_fail_hcp.setdefault(seat, 0)
            self.seat_fail_shape.setdefault(seat, 0)

    @property
    def success_rate(self) -> float:
        """Fraction of boards that succeeded."""
        if self.num_boards_requested == 0:
            return 0.0
        return self.num_boards_succeeded / self.num_boards_requested

    @property
    def pain_share(self) -> Dict[Seat, float]:
        """
        Fraction of total failures attributed to each seat.

        A seat with high pain_share is the primary bottleneck.
        """
        total = sum(self.seat_fail_as_seat.values())
        if total == 0:
            return {seat: 0.0 for seat in ("N", "E", "S", "W")}
        return {seat: count / total for seat, count in self.seat_fail_as_seat.items()}

    @property
    def hardest_seat(self) -> Optional[Seat]:
        """The seat with the highest pain_share, or None if no failures."""
        ps = self.pain_share
        if all(v == 0.0 for v in ps.values()):
            return None
        return max(ps, key=lambda s: ps[s])

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "profile_name": self.profile_name,
            "num_boards_requested": self.num_boards_requested,
            "num_boards_succeeded": self.num_boards_succeeded,
            "num_boards_failed": self.num_boards_failed,
            "total_attempts": self.total_attempts,
            "success_rate": self.success_rate,
            "hardest_seat": self.hardest_seat,
            "pain_share": self.pain_share,
            "seat_fail_as_seat": self.seat_fail_as_seat,
            "seat_fail_global_other": self.seat_fail_global_other,
            "seat_fail_global_unchecked": self.seat_fail_global_unchecked,
            "seat_fail_hcp": self.seat_fail_hcp,
            "seat_fail_shape": self.seat_fail_shape,
        }

    def to_json(self, path: Path, indent: int = 2) -> None:
        """Write report to JSON file."""
        path.write_text(json.dumps(self.to_dict(), indent=indent))

    def to_csv(self, path: Path) -> None:
        """
        Write report to CSV file.

        Format: one row per seat with all metrics.
        """
        rows = []
        ps = self.pain_share
        for seat in ("N", "E", "S", "W"):
            rows.append({
                "seat": seat,
                "fail_as_seat": self.seat_fail_as_seat[seat],
                "fail_global_other": self.seat_fail_global_other[seat],
                "fail_global_unchecked": self.seat_fail_global_unchecked[seat],
                "fail_hcp": self.seat_fail_hcp[seat],
                "fail_shape": self.seat_fail_shape[seat],
                "pain_share": ps[seat],
            })

        with path.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    def summary(self) -> str:
        """Return a human-readable summary string."""
        lines = [
            f"Profile: {self.profile_name}",
            f"Boards: {self.num_boards_succeeded}/{self.num_boards_requested} "
            f"({self.success_rate:.1%} success)",
            f"Total attempts: {self.total_attempts}",
            f"Hardest seat: {self.hardest_seat or 'N/A'}",
            "",
            "Per-seat failures (as_seat):",
        ]
        for seat in ("N", "E", "S", "W"):
            ps = self.pain_share[seat]
            lines.append(f"  {seat}: {self.seat_fail_as_seat[seat]:6d} ({ps:.1%})")
        return "\n".join(lines)


def collect_failure_attribution(
    profile: HandProfile,
    num_boards: int,
    seed: int = 0,
    max_attempts: Optional[int] = None,
) -> FailureAttributionReport:
    """
    Run deal generation and collect failure attribution data.

    Args:
        profile: The hand profile to generate boards for
        num_boards: Number of boards to attempt
        seed: Random seed for reproducibility
        max_attempts: Override MAX_BOARD_ATTEMPTS (default: use module default)

    Returns:
        FailureAttributionReport with aggregated failure data
    """
    # Initialize accumulators
    total_as_seat: Dict[Seat, int] = {s: 0 for s in ("N", "E", "S", "W")}
    total_global_other: Dict[Seat, int] = {s: 0 for s in ("N", "E", "S", "W")}
    total_global_unchecked: Dict[Seat, int] = {s: 0 for s in ("N", "E", "S", "W")}
    total_hcp: Dict[Seat, int] = {s: 0 for s in ("N", "E", "S", "W")}
    total_shape: Dict[Seat, int] = {s: 0 for s in ("N", "E", "S", "W")}

    # Track latest snapshot from each board (for accumulation)
    latest_as_seat: Dict[Seat, int] = {}
    latest_global_other: Dict[Seat, int] = {}
    latest_global_unchecked: Dict[Seat, int] = {}
    latest_hcp: Dict[Seat, int] = {}
    latest_shape: Dict[Seat, int] = {}

    total_attempts = 0
    boards_succeeded = 0
    boards_failed = 0

    # Hook to capture attribution data
    def attribution_hook(
        _profile: Any,
        _board_number: int,
        attempt_number: int,
        seat_fail_as_seat: Dict[Seat, int],
        seat_fail_global_other: Dict[Seat, int],
        seat_fail_global_unchecked: Dict[Seat, int],
        seat_fail_hcp: Dict[Seat, int],
        seat_fail_shape: Dict[Seat, int],
    ) -> None:
        nonlocal latest_as_seat, latest_global_other, latest_global_unchecked
        nonlocal latest_hcp, latest_shape, total_attempts
        latest_as_seat = dict(seat_fail_as_seat)
        latest_global_other = dict(seat_fail_global_other)
        latest_global_unchecked = dict(seat_fail_global_unchecked)
        latest_hcp = dict(seat_fail_hcp)
        latest_shape = dict(seat_fail_shape)
        total_attempts = attempt_number

    # Save and set hook
    old_hook = getattr(dg, "_DEBUG_ON_ATTEMPT_FAILURE_ATTRIBUTION", None)
    dg._DEBUG_ON_ATTEMPT_FAILURE_ATTRIBUTION = attribution_hook

    # Save and optionally override max attempts
    old_max = dg.MAX_BOARD_ATTEMPTS
    if max_attempts is not None:
        dg.MAX_BOARD_ATTEMPTS = max_attempts

    try:
        rng = random.Random(seed)

        for board_num in range(1, num_boards + 1):
            # Reset latest snapshots
            latest_as_seat = {}
            latest_global_other = {}
            latest_global_unchecked = {}
            latest_hcp = {}
            latest_shape = {}

            # Attempt to build the deal (v2 is the active production builder).
            result = dg._build_single_constrained_deal_v2(
                rng=rng,
                profile=profile,
                board_number=board_num,
            )

            if result is not None:
                boards_succeeded += 1
            else:
                boards_failed += 1

            # Accumulate the final snapshot from this board
            for seat in ("N", "E", "S", "W"):
                total_as_seat[seat] += latest_as_seat.get(seat, 0)
                total_global_other[seat] += latest_global_other.get(seat, 0)
                total_global_unchecked[seat] += latest_global_unchecked.get(seat, 0)
                total_hcp[seat] += latest_hcp.get(seat, 0)
                total_shape[seat] += latest_shape.get(seat, 0)

    finally:
        # Restore original hook and max attempts
        if old_hook is not None:
            dg._DEBUG_ON_ATTEMPT_FAILURE_ATTRIBUTION = old_hook
        else:
            dg._DEBUG_ON_ATTEMPT_FAILURE_ATTRIBUTION = None
        dg.MAX_BOARD_ATTEMPTS = old_max

    return FailureAttributionReport(
        profile_name=profile.profile_name,
        num_boards_requested=num_boards,
        num_boards_succeeded=boards_succeeded,
        num_boards_failed=boards_failed,
        total_attempts=total_attempts,
        seat_fail_as_seat=total_as_seat,
        seat_fail_global_other=total_global_other,
        seat_fail_global_unchecked=total_global_unchecked,
        seat_fail_hcp=total_hcp,
        seat_fail_shape=total_shape,
    )
