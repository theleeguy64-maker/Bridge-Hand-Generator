# tests/test_profile_e_v2_hcp_gate.py
"""
End-to-end tests for Profile E with the v2 builder and HCP feasibility gate.

Profile E: North needs exactly 6 spades and 10-12 total HCP.
Other seats (E/S/W) are wide open.

These tests verify that:
  1. The HCP feasibility gate is active (canary).
  2. The v2 builder can generate Profile E boards successfully.
  3. The full generate_deals() pipeline works for Profile E.

NOT gated behind an environment variable — runs in the normal test suite.
Profile E with v2 shape help typically generates in <500 attempts per board.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

import bridge_engine.deal_generator as dg
from bridge_engine.deal_generator import (
    ENABLE_HCP_FEASIBILITY_CHECK,
    _build_single_constrained_deal_v2,
    generate_deals,
    _card_hcp,
)
from bridge_engine.hand_profile import HandProfile
from bridge_engine.setup_env import run_setup


PROFILE_DIR = Path("profiles")
PROFILE_E_FNAME = (
    "Profile_E_Test_-_tight_and_suit_point_constraint_plus_v0.1.json"
)


def _load_profile_e() -> HandProfile:
    """Load Profile E from disk."""
    path = PROFILE_DIR / PROFILE_E_FNAME
    if not path.exists():
        pytest.skip(f"Missing profile file: {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    return HandProfile.from_dict(raw)


def _count_spades(hand: list) -> int:
    """Count spade cards in a hand.  Card format: rank+suit, e.g. 'AS'."""
    return sum(1 for c in hand if len(c) >= 2 and c[1] == "S")


def _hand_hcp(hand: list) -> int:
    """Sum HCP for all cards in a hand."""
    return sum(_card_hcp(c) for c in hand)


# ---------------------------------------------------------------------------
# Canary: ensure the gate is active
# ---------------------------------------------------------------------------


class TestHcpGateCanary:
    """Guard against accidental gate regression."""

    def test_hcp_feasibility_gate_is_on(self):
        """ENABLE_HCP_FEASIBILITY_CHECK should be True in production."""
        assert ENABLE_HCP_FEASIBILITY_CHECK is True, (
            "HCP feasibility gate is OFF — flip to True in deal_generator.py"
        )


# ---------------------------------------------------------------------------
# v2 builder direct: Profile E across multiple boards
# ---------------------------------------------------------------------------


class TestProfileEV2Builder:
    """Call _build_single_constrained_deal_v2() directly on Profile E."""

    NUM_BOARDS = 10

    def test_generates_boards_successfully(self):
        """v2 builder should generate all boards without raising."""
        profile = _load_profile_e()
        for board_number in range(1, self.NUM_BOARDS + 1):
            rng = random.Random(42_000 + board_number)
            deal = _build_single_constrained_deal_v2(
                rng=rng,
                profile=profile,
                board_number=board_number,
            )
            assert deal is not None, f"Board {board_number} returned None"

    def test_north_has_exactly_6_spades(self):
        """North's hand must have exactly 6 spades per Profile E constraints."""
        profile = _load_profile_e()
        for board_number in range(1, self.NUM_BOARDS + 1):
            rng = random.Random(42_000 + board_number)
            deal = _build_single_constrained_deal_v2(
                rng=rng,
                profile=profile,
                board_number=board_number,
            )
            n_spades = _count_spades(deal.hands["N"])
            assert n_spades == 6, (
                f"Board {board_number}: North has {n_spades} spades, expected 6"
            )

    def test_north_has_10_to_12_hcp(self):
        """North's hand must have 10-12 total HCP per Profile E constraints."""
        profile = _load_profile_e()
        for board_number in range(1, self.NUM_BOARDS + 1):
            rng = random.Random(42_000 + board_number)
            deal = _build_single_constrained_deal_v2(
                rng=rng,
                profile=profile,
                board_number=board_number,
            )
            n_hcp = _hand_hcp(deal.hands["N"])
            assert 10 <= n_hcp <= 12, (
                f"Board {board_number}: North has {n_hcp} HCP, expected 10-12"
            )

    def test_all_hands_have_13_cards(self):
        """Every seat should have exactly 13 cards."""
        profile = _load_profile_e()
        for board_number in range(1, self.NUM_BOARDS + 1):
            rng = random.Random(42_000 + board_number)
            deal = _build_single_constrained_deal_v2(
                rng=rng,
                profile=profile,
                board_number=board_number,
            )
            for seat in ("N", "E", "S", "W"):
                assert len(deal.hands[seat]) == 13, (
                    f"Board {board_number}: {seat} has "
                    f"{len(deal.hands[seat])} cards"
                )


# ---------------------------------------------------------------------------
# Full pipeline: generate_deals() with Profile E
# ---------------------------------------------------------------------------


class TestProfileEFullPipeline:
    """End-to-end through generate_deals() — the production entry point."""

    NUM_BOARDS = 5

    def test_generate_deals_succeeds(self, tmp_path):
        """generate_deals() should produce the requested number of boards."""
        profile = _load_profile_e()
        setup = run_setup(
            base_dir=tmp_path,
            owner="TestOwner",
            profile_name="Profile E e2e test",
            ask_seed_choice=False,
            use_seeded_default=True,
        )
        deal_set = generate_deals(
            setup, profile, self.NUM_BOARDS, enable_rotation=False
        )
        assert len(deal_set.deals) == self.NUM_BOARDS

    def test_north_constraints_via_pipeline(self, tmp_path):
        """North should satisfy 6 spades + 10-12 HCP through full pipeline."""
        profile = _load_profile_e()
        setup = run_setup(
            base_dir=tmp_path,
            owner="TestOwner",
            profile_name="Profile E e2e test",
            ask_seed_choice=False,
            use_seeded_default=True,
        )
        deal_set = generate_deals(
            setup, profile, self.NUM_BOARDS, enable_rotation=False
        )
        for deal in deal_set.deals:
            n_spades = _count_spades(deal.hands["N"])
            n_hcp = _hand_hcp(deal.hands["N"])
            assert n_spades == 6, (
                f"Board {deal.board_number}: North {n_spades} spades, expected 6"
            )
            assert 10 <= n_hcp <= 12, (
                f"Board {deal.board_number}: North {n_hcp} HCP, expected 10-12"
            )
