"""Rotate a HandProfile around the table (W→N→E→S→W).

Pure data transformation: every seat reference advances one position around
the cycle. See docs/superpowers/specs/2026-04-25-rotate-profile-design.md
for the full rule set.
"""
from __future__ import annotations

ROTATE_MAP: dict[str, str] = {"W": "N", "N": "E", "E": "S", "S": "W"}


def _rotate_seat(seat: str) -> str:
    if seat not in ROTATE_MAP:
        raise ValueError(f"Invalid seat: {seat!r}")
    return ROTATE_MAP[seat]
