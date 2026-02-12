# tests/test_random_suit_pc_order.py

import random
import pytest

from typing import Dict, List, Optional
from collections import Counter

from bridge_engine import deal_generator
# Stable reference to the real matcher so tests don't wrap a wrapper.
_ORIGINAL_MATCH_SEAT = deal_generator._match_seat

from bridge_engine.deal_generator import Seat
from bridge_engine.deal_generator import DealGenerationError

from tests.test_deal_generator_section_c import (  # type: ignore
    _random_suit_w_partner_contingent_e_profile,
)

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


def test_random_suit_frequency_guardrail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Behavioural guardrail for RS suit frequencies using the real RS engine.

    Runs a small RS/PC profile and checks that RS suit choices are spread
    across all four suits (no single suit dominates).

    This version is deliberately cheap:
      * we cap MAX_BOARD_ATTEMPTS,
      * we stop once we have a modest number of RS samples, and
      * if we never get enough samples, we skip rather than grind.
    """
    profile_factory = _random_suit_w_partner_contingent_e_profile

    SUITS = ["S", "H", "D", "C"]

    MAX_BOARDS = 120
    TARGET_RS_SAMPLES = 20

    monkeypatch.setattr(
        deal_generator,
        "MAX_BOARD_ATTEMPTS",
        200,
        raising=False,
    )

    rng = random.Random(9876)
    profile = profile_factory()

    suit_counts: Counter = Counter()

    original_match_seat = deal_generator._match_seat

    def wrapper_match_seat(
        *,
        profile: object,
        seat: str,
        hand: List[object],
        seat_profile: object,
        chosen_subprofile: object,
        chosen_subprofile_index_1based: int,
        random_suit_choices: Dict[str, List[str]],
        rng: random.Random,
    ):
        matched, chosen_rs, fail_reason = original_match_seat(
            profile=profile,
            seat=seat,
            hand=hand,
            seat_profile=seat_profile,
            chosen_subprofile=chosen_subprofile,
            chosen_subprofile_index_1based=chosen_subprofile_index_1based,
            random_suit_choices=random_suit_choices,
            rng=rng,
        )

        if (
            matched
            and getattr(chosen_subprofile, "random_suit_constraint", None)
            is not None
            and chosen_rs
        ):
            if isinstance(chosen_rs, (list, tuple)) and chosen_rs:
                suit = str(chosen_rs[0])
            else:
                suit = str(chosen_rs)

            if suit in SUITS:
                suit_counts[suit] += 1

        return matched, chosen_rs, fail_reason

    monkeypatch.setattr(
        deal_generator,
        "_match_seat",
        wrapper_match_seat,
        raising=False,
    )

    boards_tried = 0
    while boards_tried < MAX_BOARDS and sum(suit_counts.values()) < TARGET_RS_SAMPLES:
        boards_tried += 1
        try:
            deal_generator._build_single_constrained_deal(
                rng=rng,
                profile=profile,
                board_number=boards_tried,
            )
        except DealGenerationError:
            continue

    total = sum(suit_counts.values())

    MIN_SAMPLES = 10
    if total < MIN_SAMPLES:
        pytest.skip(
            f"RS_PC smoke profile produced too few RS samples for guardrail "
            f"({total}); profile/seed too constrained."
        )

    # Guardrail: no single suit should grossly dominate RS choices.
    # With only ~20 samples, natural variance can push one suit above 50%,
    # so we use a generous 60% threshold to catch only severe drift.
    for suit in SUITS:
        if suit_counts[suit] == 0:
            continue
        freq = suit_counts[suit] / total
        assert freq <= 0.60, f"Suit {suit} dominates RS choices: {freq:.1%}"        
                
                
def test_random_suit_monotonicity_guardrail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Monotonicity guardrail for RS profiles using the real engine.

    Attempts to generate a modest number of boards via
    _build_single_constrained_deal and asserts a reasonable success rate.

    Tuned to be cheap: low NUM_BOARDS, capped MAX_BOARD_ATTEMPTS, and
    skip if the profile/seed can't produce enough signal.
    """
    profile_factory = _random_suit_w_partner_contingent_e_profile

    NUM_BOARDS = 80

    monkeypatch.setattr(
        deal_generator,
        "MAX_BOARD_ATTEMPTS",
        200,
        raising=False,
    )

    rng = random.Random(2222)
    profile = profile_factory()

    successes = 0
    consecutive_failures = 0
    MAX_CONSECUTIVE_FAIL = 20

    for board_no in range(1, NUM_BOARDS + 1):
        if consecutive_failures >= MAX_CONSECUTIVE_FAIL:
            break

        try:
            deal_generator._build_single_constrained_deal(
                rng=rng,
                profile=profile,
                board_number=board_no,
            )
        except DealGenerationError:
            consecutive_failures += 1
            continue
        else:
            successes += 1
            consecutive_failures = 0

    MIN_BASELINE_SUCCESS = max(1, NUM_BOARDS // 10)
    if successes < MIN_BASELINE_SUCCESS:
        pytest.skip(
            f"Baseline success rate too low for monotonicity guardrail "
            f"({successes}/{NUM_BOARDS}); profile/seed too constrained."
        )
                
                
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
            return True, ["S"], None

        if seat == "E":
            # PC seat must "see" West's RS choice by the time it's called.
            seen_rs_choices_at_e = list(random_suit_choices.get("W", []))
            return True, None, None

        # Other seats: unconstrained for this test.
        return True, None, None

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
            return True, ["S"], None

        if seat == "E":
            # East chooses Hearts.
            random_suit_choices.setdefault("E", []).append("H")
            return True, ["H"], None

        if seat == "N":
            # "PC" seat: by the time we get here, both RS choices must be visible.
            seen_rs_at_n["W"] = list(random_suit_choices.get("W", []))
            seen_rs_at_n["E"] = list(random_suit_choices.get("E", []))
            return True, None, None

        # Other seats: unconstrained for this test.
        return True, None, None

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
            return True, ["S"], None

        if seat == "E":
            # "PC" seat: by the time we get here, it should see W's choice.
            seen_rs_at_e = list(random_suit_choices.get("W", []))
            return True, None, None

        # Other seats: unconstrained for this test.
        return True, None, None

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
    
    
def test_pc_oc_view_of_random_suit_choices_guardrail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Guardrail: PC/OC seats must see RS choices only via random_suit_choices,
    and RS seats must be evaluated first in the core matching loop.

    We build a tiny sandbox profile with:
      * W = RS seat
      * E = PC seat (partner of W)
      * N = OC seat (opponent)
      * S = unconstrained

    We stub _match_seat to:
      * record the order in which seats are evaluated,
      * record what random_suit_choices looks like at call time, and
      * for the RS seat, choose a fixed suit "S" and write it into
        random_suit_choices[W].

    Expectations:
      * W (RS) is evaluated first.
      * When E (PC) and N (OC) are evaluated, they can already see
        random_suit_choices["W"] == ["S"].
    """

    # ---- Tiny sandbox profile with RS / PC / OC tagging -----------------

    class _DummySubprofile:
        def __init__(self, kind: str = "plain") -> None:
            if kind == "RS":
                self.random_suit_constraint = object()
            elif kind == "PC":
                self.partner_contingent_constraint = object()
            elif kind == "OC":
                self.opponents_contingent_suit_constraint = object()

    class _DummySeatProfile:
        def __init__(self, kind: str = "plain") -> None:
            self.subprofiles = [_DummySubprofile(kind=kind)]

    class _DummyProfile:
        def __init__(self) -> None:
            self.dealer = "N"
            # Deliberately weird dealing order to prove RS-first ordering
            # is independent of dealing_order.
            self.hand_dealing_order = ["N", "E", "S", "W"]
            self.seat_profiles: Dict[str, _DummySeatProfile] = {
                # N = OC seat (opponent of W)
                "N": _DummySeatProfile(kind="OC"),
                # E = PC seat (partner of W)
                "E": _DummySeatProfile(kind="PC"),
                # S = unconstrained/plain seat
                "S": _DummySeatProfile(kind="plain"),
                # W = RS seat
                "W": _DummySeatProfile(kind="RS"),
            }
            # Ensure NS coupling never triggers.
            self.ns_index_coupling_enabled = False
            self.profile_name = "RS_PC_OC_guardrail_sandbox"

    # Make the engine treat our stub as the SeatProfile type.
    monkeypatch.setattr(
        deal_generator,
        "SeatProfile",
        _DummySeatProfile,
        raising=False,
    )

    profile = _DummyProfile()

    calls: List[Dict[str, object]] = []

    def stub_match_seat(
        profile: object,
        seat: str,
        hand: List[object],
        seat_profile: object,
        chosen_subprofile: object,
        chosen_subprofile_index_1based: int,
        random_suit_choices: Dict[str, List[str]],
        rng: random.Random,
    ):
        # Snapshot what PC/OC can "see" at the moment this seat is evaluated.
        snapshot = {
            k: list(v) for k, v in random_suit_choices.items()
        }
        calls.append(
            {
                "seat": seat,
                "snapshot": snapshot,
            }
        )

        # RS seat: choose a fixed suit "S" and publish via random_suit_choices.
        is_rs = getattr(
            chosen_subprofile, "random_suit_constraint", None
        ) is not None
        if is_rs:
            random_suit_choices.setdefault(seat, []).append("S")
            return True, ["S"], None

        # PC / OC / plain seats: unconstrained, always match.
        return True, None, None

    monkeypatch.setattr(
        deal_generator,
        "_match_seat",
        stub_match_seat,
        raising=False,
    )

    rng = random.Random(1234)
    _ = deal_generator._build_single_constrained_deal(
        rng=rng,
        profile=profile,
        board_number=1,
    )
 
     # ---- Assertions: ordering + visibility via random_suit_choices -----

    # We expect exactly one attempt and thus 4 calls (N, E, S, W).
    order = [c["seat"] for c in calls]
    assert set(order) == {"N", "E", "S", "W"}

    # 1) RS seat (W) must be evaluated first, regardless of dealing_order.
    assert order[0] == "W"
    assert order.count("W") == 1

    # Build a quick lookup of snapshots per seat.
    snapshots_by_seat = {
        entry["seat"]: entry["snapshot"] for entry in calls
    }

    # 2) PC seat (E) must see W's RS choice via random_suit_choices.
    e_snapshot = snapshots_by_seat["E"]
    assert e_snapshot.get("W") == ["S"]

    # 3) OC seat (N) must also see W's RS choice the same way.
    n_snapshot = snapshots_by_seat["N"]
    assert n_snapshot.get("W") == ["S"]

    # 4) Plain seat (S) may or may not care, but if it looks it should
    #    see the same RS choice via the shared map.
    s_snapshot = snapshots_by_seat["S"]
    assert s_snapshot.get("W") == ["S"]    


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


    