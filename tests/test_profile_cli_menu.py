from __future__ import annotations

import builtins
from pathlib import Path
from typing import List, Tuple

from bridge_engine.hand_profile import HandProfile
from bridge_engine import profile_cli as pc


def make_profile(name: str, version: str | None = None) -> HandProfile:
    return HandProfile(
        profile_name=name,
        description="Test",
        dealer="N",
        hand_dealing_order=["N", "E", "S", "W"],
        tag="Opener",
        seat_profiles={},
        author="Test",
        version=version,
    )


def test_choose_profile_simple(monkeypatch):
    p1 = make_profile("ProfileA", "0.1")
    p2 = make_profile("ProfileB", "0.2")

    # Match current _choose_profile signature: List[Tuple[Path, HandProfile]]
    profiles: List[Tuple[Path, HandProfile]] = [
        (Path("/fake/A.json"), p1),
        (Path("/fake/B.json"), p2),
    ]

    # ProfileB (v0.2) sorts before ProfileA (v0.1) — highest version first
    def fake_input(prompt: str) -> str:
        return "1"

    monkeypatch.setattr(builtins, "input", fake_input)

    result = pc._choose_profile(profiles)
    assert result is not None
    path, profile = result
    assert path == Path("/fake/B.json")
    assert profile.profile_name == "ProfileB"


def test_choose_profile_cancel(monkeypatch):
    p = make_profile("P", "1")
    profiles: List[Tuple[Path, HandProfile]] = [
        (Path("/fake/P.json"), p),
    ]

    def fake_input(prompt: str) -> str:
        return ""  # Enter → cancel

    monkeypatch.setattr(builtins, "input", fake_input)

    result = pc._choose_profile(profiles)
    assert result is None
