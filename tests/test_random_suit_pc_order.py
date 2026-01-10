# tests/test_random_suit_pc_order.py

import random
from typing import Dict, List, Optional

import pytest

from bridge_engine import deal_generator
from bridge_engine.deal_generator import Seat

# ---------------------------------------------------------------------------
# Shared dummy model for the single-RS + PC test
# ---------------------------------------------------------------------------


class DummySubprofile:
    """
    Minimal subprofile stub.

    We only care about the presence of `random_suit_constraint` to mark a seat
    as "Random Suit" for the core matching loop.
    """

    def __init__(self, is_rs: bool = False) -> None:
        if is_rs:
            # The core loop in _build_single_constrained_deal checks for this
            # attribute to classify RS seats.
            self.random_suit_constraint = object()


class DummySeatProfile:
    """
    Minimal seat profile with exactly one subprofile.

    `is_rs` controls whether that subprofile is treated as a Random-Suit seat
    by the core loop.
    """

    def __init__(self, is_rs: bool = False) -> None:
        self.subprofiles = [DummySubprofile(is_rs=is_rs)]


class DummyProfile:
    """
    Minimal duck-typed profile for exercising RS → PC ordering.

    We deliberately:
      * supply `seat_profiles` keyed by "N", "E", "S", "W"
      * set West ("W") as an RS seat
      * avoid NS index coupling, so `ns_driver_seat` is never consulted
    """

    def __init__(self) -> None:
        self.dealer: Seat = "N"
        self.hand_dealing_order: List[Seat] = ["N", "E", "S", "W"]
        self.seat_profiles: Dict[Seat, DummySeatProfile] = {
            "N": DummySeatProfile(is_rs=False),
            "E": DummySeatProfile(is_rs=False),  # treated as PC by fake matcher
            "S": DummySeatProfile(is_rs=False),
            "W": DummySeatProfile(is_rs=True),   # RS seat
        }
        self.ns_index_coupling_enabled = False
        self.profile_name = "RS_PC_single_sandbox"


# ---------------------------------------------------------------------------
# 1) Single RS seat (W) + PC seat (E): PC must see W's RS choice
# ---------------------------------------------------------------------------


def test_partner_contingent_sees_partner_random_suit_choice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Sanity check on evaluation order inside _build_single_constrained_deal:

      * West ("W") is treated as a Random Suit seat.
      * East ("E") is treated as a Partner-Contingent seat.

    The deal builder should:

      1. Call _match_seat for W *before* calling it for E.
      2. Allow W's _match_seat call to record its RS choice into
         random_suit_choices["W"].
      3. When E's _match_seat runs, random_suit_choices["W"] must already
         contain that RS choice.

    This test does not rely on the real RandomSuitConstraint / PC semantics;
    it only asserts the ordering and the flow of RS information via
    random_suit_choices.
    """
    profile = DummyProfile()

    # Make the generator treat DummySeatProfile as its SeatProfile type.
    monkeypatch.setattr(deal_generator, "SeatProfile", DummySeatProfile)

    call_order: List[Seat] = []
    seen_rs_choices_at_e: Optional[List[str]] = None

    def fake_match_seat(
        profile: object,
        seat: Seat,
        hand: List[object],
        seat_profile: object,
        chosen_subprofile: object,
        chosen_subprofile_index_1based: int,
        random_suit_choices: Dict[Seat, List[str]],
        rng: random.Random,
    ):
        nonlocal seen_rs_choices_at_e
        call_order.append(seat)

        if seat == "W":
            # West chooses Spades and records the RS choice.
            random_suit_choices.setdefault("W", []).append("S")
            return True, ["S"]

        if seat == "E":
            # PC seat must "see" West's RS choice by the time it's called.
            seen_rs_choices_at_e = list(random_suit_choices.get("W", []))
            return True, None

        # Other seats: unconstrained for this test.
        return True, None

    monkeypatch.setattr(deal_generator, "_match_seat", fake_match_seat)

    rng = random.Random(1234)

    # If ordering is wrong, either:
    #   * the assertions in fake_match_seat will fail, or
    #   * we won't reach a successful deal.
    deal = deal_generator._build_single_constrained_deal(
        rng=rng,
        profile=profile,
        board_number=1,
    )

    # Basic sanity: a deal was produced.
    assert deal is not None

    # 1) West must be matched before East.
    assert "W" in call_order and "E" in call_order
    assert call_order.index("W") < call_order.index("E")

    # 2) By the time East ran, it must have seen West's RS choice.
    assert seen_rs_choices_at_e == ["S"]


# ---------------------------------------------------------------------------
# 2) Two RS seats (W, E) + PC seat (N): PC must see both RS choices
# ---------------------------------------------------------------------------


def test_two_random_suit_seats_visible_to_pc_partner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    In a board with two Random-Suit seats (W, E) and a partner-contingent seat (N),
    both RS seats must run *before* N, and by the time N's matcher is called,
    random_suit_choices must already contain both RS choices.

    This is a pure ordering / visibility check on the core loop:
      - rs_seats are processed first,
      - then all other seats (including any PC seats).
    """

    # --- Local minimal dummy model -----------------------------------------
    class _DummySubprofile:
        def __init__(self, is_rs: bool = False) -> None:
            if is_rs:
                # Presence of this attribute marks the seat as "Random Suit"
                # for the core loop.
                self.random_suit_constraint = object()

    class _DummySeatProfile:
        def __init__(self, is_rs: bool = False) -> None:
            self.subprofiles = [_DummySubprofile(is_rs=is_rs)]

    class _DummyProfile:
        def __init__(self) -> None:
            # N will be treated as a "PC" seat by our fake matcher only.
            # W and E are RS seats (via their chosen_subprofile).
            self.dealer: Seat = "N"
            self.hand_dealing_order: List[Seat] = ["N", "E", "S", "W"]
            self.seat_profiles: Dict[Seat, _DummySeatProfile] = {
                "N": _DummySeatProfile(is_rs=False),
                "E": _DummySeatProfile(is_rs=True),
                "S": _DummySeatProfile(is_rs=False),
                "W": _DummySeatProfile(is_rs=True),
            }
            # Make sure we never trigger NS coupling.
            self.ns_index_coupling_enabled = False
            self.profile_name = "RS_PC_multi_sandbox"

    profile = _DummyProfile()

    # Make the generator treat our stub as its SeatProfile type.
    monkeypatch.setattr(deal_generator, "SeatProfile", _DummySeatProfile)

    call_order: List[Seat] = []
    seen_rs_at_n: Dict[Seat, List[str]] = {}

    def fake_match_seat(
        profile: object,
        seat: Seat,
        hand: List[object],
        seat_profile: object,
        chosen_subprofile: object,
        chosen_subprofile_index_1based: int,
        random_suit_choices: Dict[Seat, List[str]],
        rng: random.Random,
    ):
        call_order.append(seat)

        if seat == "W":
            # West chooses Spades.
            random_suit_choices.setdefault("W", []).append("S")
            return True, ["S"]

        if seat == "E":
            # East chooses Hearts.
            random_suit_choices.setdefault("E", []).append("H")
            return True, ["H"]

        if seat == "N":
            # "PC" seat: by the time we get here, both RS choices must be visible.
            seen_rs_at_n["W"] = list(random_suit_choices.get("W", []))
            seen_rs_at_n["E"] = list(random_suit_choices.get("E", []))
            return True, None

        # Other seats: unconstrained for this test.
        return True, None

    monkeypatch.setattr(deal_generator, "_match_seat", fake_match_seat)

    rng = random.Random(4321)
    # If ordering/flow is wrong, fake_match_seat assertions or dict lookups
    # will fail or we won't reach a successful deal.
    deal_generator._build_single_constrained_deal(
        rng=rng,
        profile=profile,
        board_number=1,
    )

    # 1) RS seats must both run before N.
    assert "W" in call_order and "E" in call_order and "N" in call_order
    assert call_order.index("W") < call_order.index("N")
    assert call_order.index("E") < call_order.index("N")

    # 2) By the time N ran, it must have seen both RS choices.
    assert seen_rs_at_n["W"] == ["S"]
    assert seen_rs_at_n["E"] == ["H"]
    
    
def test_rs_pc_sandbox_shadow_order_and_visibility(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Shadow-mode check on a minimal RS/PC sandbox:

      * West ("W") behaves like a Random-Suit seat.
      * East ("E") behaves like a Partner-Contingent seat that looks at W's choice.

    The core loop in _build_single_constrained_deal must:
      - call W's matcher before E's, and
      - by the time E runs, random_suit_choices["W"] already contains W's choice.

    This uses a tiny dummy profile rather than the full production profile.
    """

    # --- Local minimal dummy model -----------------------------------------
    class _DummySubprofile:
        def __init__(self, is_rs: bool = False) -> None:
            if is_rs:
                # Presence of this attribute marks the seat as "Random Suit"
                # for the core loop.
                self.random_suit_constraint = object()

    class _DummySeatProfile:
        def __init__(self, is_rs: bool = False) -> None:
            self.subprofiles = [_DummySubprofile(is_rs=is_rs)]

    class _DummyProfile:
        def __init__(self) -> None:
            # W is the RS seat; E is the "PC" seat for this test.
            self.dealer = "N"
            self.hand_dealing_order = ["N", "E", "S", "W"]
            self.seat_profiles: Dict[str, _DummySeatProfile] = {
                "N": _DummySeatProfile(is_rs=False),
                "E": _DummySeatProfile(is_rs=False),
                "S": _DummySeatProfile(is_rs=False),
                "W": _DummySeatProfile(is_rs=True),
            }
            # Make sure we never trigger NS coupling.
            self.ns_index_coupling_enabled = False
            self.profile_name = "RS_PC_shadow_sandbox"

    profile = _DummyProfile()

    # Make the generator treat our stub as its SeatProfile type.
    monkeypatch.setattr(deal_generator, "SeatProfile", _DummySeatProfile)

    call_order: List[str] = []
    seen_rs_at_e: Optional[List[str]] = None

    def fake_match_seat(
        profile: object,
        seat: str,
        hand: List[object],
        seat_profile: object,
        chosen_subprofile: object,
        chosen_subprofile_index_1based: int,
        random_suit_choices: Dict[str, List[str]],
        rng: random.Random,
    ):
        nonlocal seen_rs_at_e
        call_order.append(seat)

        if seat == "W":
            # West chooses Spades.
            random_suit_choices.setdefault("W", []).append("S")
            return True, ["S"]

        if seat == "E":
            # "PC" seat: by the time we get here, it should see W's choice.
            seen_rs_at_e = list(random_suit_choices.get("W", []))
            return True, None

        # Other seats: unconstrained for this test.
        return True, None

    monkeypatch.setattr(deal_generator, "_match_seat", fake_match_seat)

    rng = random.Random(4321)
    deal_generator._build_single_constrained_deal(
        rng=rng,
        profile=profile,
        board_number=1,
    )

    # 1) W must be matched before E.
    assert "W" in call_order and "E" in call_order
    assert call_order.index("W") < call_order.index("E")

    # 2) By the time E ran, it must have seen W's RS choice.
    assert seen_rs_at_e == ["S"]


def test_rs_pc_sandbox_viability_summary_smoke() -> None:
    """
    Smoke test: we can collect a viability summary from synthetic
    fail/seen counts, and the buckets are one of the known labels.

    This is independent of any particular profile; we just pretend "W"
    and "E" are the RS/PC sandbox seats.
    """
    seat_fail_counts = {"W": 10, "E": 3}
    seat_seen_counts = {"W": 20, "E": 10}

    summary = deal_generator._summarize_profile_viability(
        seat_fail_counts,
        seat_seen_counts,
    )

    # We should get back the same seat keys.
    assert set(summary.keys()) == {"W", "E"}

    # Buckets must be one of the labels used by classify_viability.
    for bucket in summary.values():
        assert bucket in {"unknown", "likely", "borderline", "unlikely", "unviable"}


def test_nonstandard_shadow_hook_invoked_for_rs_pc_sandbox(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Shadow-mode smoke test for ENABLE_CONSTRUCTIVE_HELP_NONSTANDARD:

      * Build a tiny dummy profile with a non-standard (RS) seat.
      * Enable the non-standard shadow flag.
      * Install a debug hook via _DEBUG_NONSTANDARD_CONSTRUCTIVE_SHADOW.
      * Ensure the hook is invoked and receives a viability summary that
        includes the RS seat.
    """

    class _DummySubprofile:
        def __init__(self, is_rs: bool = False) -> None:
            if is_rs:
                # Mark this subprofile as Random-Suit for the core loop.
                self.random_suit_constraint = object()

    class _DummySeatProfile:
        def __init__(self, is_rs: bool = False) -> None:
            self.subprofiles = [_DummySubprofile(is_rs=is_rs)]

    class _DummyProfile:
        def __init__(self) -> None:
            self.dealer = "N"
            self.hand_dealing_order = ["N", "E", "S", "W"]
            self.seat_profiles: Dict[str, _DummySeatProfile] = {
                "N": _DummySeatProfile(is_rs=False),
                "E": _DummySeatProfile(is_rs=False),
                "S": _DummySeatProfile(is_rs=False),
                "W": _DummySeatProfile(is_rs=True),  # RS / non-standard seat
            }
            # Ensure NS coupling never triggers.
            self.ns_index_coupling_enabled = False
            self.profile_name = "RS_PC_shadow_probe_sandbox"

    profile = _DummyProfile()

    # Treat our stub as the SeatProfile type used by the engine.
    monkeypatch.setattr(deal_generator, "SeatProfile", _DummySeatProfile)

    # Always succeed when matching seats; we only care that the shadow hook runs.
    def always_match(
        profile: object,
        seat: str,
        hand: List[object],
        seat_profile: object,
        chosen_subprofile: object,
        chosen_subprofile_index_1based: int,
        random_suit_choices: Dict[str, List[str]],
        rng: random.Random,
    ):
        return True, None

    monkeypatch.setattr(deal_generator, "_match_seat", always_match)

    # Enable non-standard shadow probing and capture hook calls.
    monkeypatch.setattr(
        deal_generator,
        "ENABLE_CONSTRUCTIVE_HELP_NONSTANDARD",
        True,
    )

    calls: List[Dict[str, object]] = []

    def shadow_hook(
        profile_arg,
        board_number,
        attempt_number,
        chosen_indices,
        seat_fail_counts,
        seat_seen_counts,
        viability_summary,
    ):
        calls.append(
            {
                "profile_name": getattr(profile_arg, "profile_name", ""),
                "board_number": board_number,
                "attempt_number": attempt_number,
                "viability_summary": dict(viability_summary),
            }
        )

    monkeypatch.setattr(
        deal_generator,
        "_DEBUG_NONSTANDARD_CONSTRUCTIVE_SHADOW",
        shadow_hook,
        raising=False,
    )

    rng = random.Random(9999)
    deal = deal_generator._build_single_constrained_deal(
        rng=rng,
        profile=profile,
        board_number=1,
    )

    # Sanity: we produced some deal object (we don't care about its contents here).
    assert deal is not None

    # The shadow hook must have been called at least once.
    assert calls, "Expected non-standard shadow hook to be invoked at least once"

    # And the viability summary should mention our RS seat "W".
    last_call = calls[-1]
    summary = last_call["viability_summary"]
    assert "W" in summary    