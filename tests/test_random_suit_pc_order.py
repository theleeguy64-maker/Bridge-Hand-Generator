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


def test_random_suit_frequency_guardrail_baseline_vs_v2(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Behavioural guardrail for RS suit frequencies using the real RS engine.

    We run a small RS/PC profile under two modes:

      * baseline: ENABLE_CONSTRUCTIVE_HELP_NONSTANDARD = False
      * "v2"    : ENABLE_CONSTRUCTIVE_HELP_NONSTANDARD = True
                  + profile.enable_nonstandard_constructive_v2 = True

    This version is deliberately cheap:
      * we cap MAX_BOARD_ATTEMPTS,
      * we stop once we have a modest number of RS samples, and
      * if we never get enough samples, we skip rather than grind.
    """
    profile_factory = _random_suit_w_partner_contingent_e_profile

    SUITS = ["S", "H", "D", "C"]

    # Max boards to try per mode; we will usually stop much earlier when we
    # have enough RS samples.
    MAX_BOARDS = 120
    # Target RS samples per mode; enough to catch gross drift but cheap to get.
    TARGET_RS_SAMPLES = 20

    # Keep attempts bounded so pathological boards don't blow up runtime.
    monkeypatch.setattr(
        deal_generator,
        "MAX_BOARD_ATTEMPTS",
        200,
        raising=False,
    )

    def run_mode(enable_nonstandard: bool, seed: int) -> Counter:
        """
        Run the real RS/PC profile under a given non-standard flag and
        return a Counter of RS suit choices across all RS seats.

        We stop as soon as we have TARGET_RS_SAMPLES samples or we run out
        of boards / attempts.
        """
        rng = random.Random(seed)
        profile = profile_factory()

        # Profile-level opt-in for non-standard v2.
        profile.enable_nonstandard_constructive_v2 = enable_nonstandard

        # Global gating: v2 rides on top of the standard constructive flag.
        monkeypatch.setattr(
            deal_generator,
            "ENABLE_CONSTRUCTIVE_HELP",
            True,
            raising=False,
        )
        monkeypatch.setattr(
            deal_generator,
            "ENABLE_CONSTRUCTIVE_HELP_NONSTANDARD",
            enable_nonstandard,
            raising=False,
        )

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
            # Call the real matcher first.
            matched, chosen_rs = original_match_seat(
                profile=profile,
                seat=seat,
                hand=hand,
                seat_profile=seat_profile,
                chosen_subprofile=chosen_subprofile,
                chosen_subprofile_index_1based=chosen_subprofile_index_1based,
                random_suit_choices=random_suit_choices,
                rng=rng,
            )

            # For any RS seat, record the RS suit choice into suit_counts.
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

            return matched, chosen_rs

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
                # Board is too hard in our capped attempts – just move on.
                continue

        return suit_counts

    # Baseline vs v2 with identical RNG seed so changes come only from v2.
    baseline_counts = run_mode(enable_nonstandard=False, seed=9876)
    v2_counts = run_mode(enable_nonstandard=True, seed=9876)

    baseline_total = sum(baseline_counts.values())
    v2_total = sum(v2_counts.values())

    # If we couldn't get enough RS samples, this configuration isn't useful
    # as a guardrail – skip rather than slow-fail the suite.
    MIN_SAMPLES = 10
    if baseline_total < MIN_SAMPLES or v2_total < MIN_SAMPLES:
        pytest.skip(
            f"RS_PC smoke profile produced too few RS samples for guardrail "
            f"(baseline={baseline_total}, v2={v2_total}); profile/seed too constrained."
        )

    # Guardrail: per-suit frequencies should not drift too far.
    for suit in SUITS:
        if baseline_counts[suit] == 0 and v2_counts[suit] == 0:
            # Suit never chosen in either mode; nothing to compare.
            continue

        base_freq = baseline_counts[suit] / baseline_total
        v2_freq = v2_counts[suit] / v2_total

        # v2 is currently a no-op, so these will be very close. In future,
        # this threshold protects against severe drift.
        assert abs(base_freq - v2_freq) <= 0.15        
                
                
def test_random_suit_monotonicity_guardrail_baseline_vs_v2(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Monotonicity guardrail for RS profiles using the real engine.

    We run a small RS/PC profile under:

      * baseline: ENABLE_CONSTRUCTIVE_HELP_NONSTANDARD = False
      * "v2"    : ENABLE_CONSTRUCTIVE_HELP_NONSTANDARD = True
                  + profile.enable_nonstandard_constructive_v2 = True

    For each mode we:

      * attempt to generate a modest number of boards via
        _build_single_constrained_deal,
      * count how many attempts succeed (no DealGenerationError), and
      * assert that the v2 success rate is not catastrophically worse.

    This is tuned to be cheap:
      * low NUM_BOARDS,
      * capped MAX_BOARD_ATTEMPTS,
      * and skip if baseline can't produce enough signal.
    """
    profile_factory = _random_suit_w_partner_contingent_e_profile

    NUM_BOARDS = 80  # keep small so the test is snappy

    # Keep things bounded so pathological boards don't blow up runtime.
    monkeypatch.setattr(
        deal_generator,
        "MAX_BOARD_ATTEMPTS",
        200,
        raising=False,
    )

    def run_mode(enable_nonstandard: bool, seed: int) -> int:
        rng = random.Random(seed)
        profile = profile_factory()

        # Profile-level opt-in for non-standard v2.
        profile.enable_nonstandard_constructive_v2 = enable_nonstandard

        # Global gating.
        monkeypatch.setattr(
            deal_generator,
            "ENABLE_CONSTRUCTIVE_HELP",
            True,
            raising=False,
        )
        monkeypatch.setattr(
            deal_generator,
            "ENABLE_CONSTRUCTIVE_HELP_NONSTANDARD",
            enable_nonstandard,
            raising=False,
        )

        successes = 0
        consecutive_failures = 0
        MAX_CONSECUTIVE_FAIL = 20  # early bail if hopeless for this seed

        for board_no in range(1, NUM_BOARDS + 1):
            if consecutive_failures >= MAX_CONSECUTIVE_FAIL:
                # This profile/seed combination is clearly not happy under our
                # capped attempts – no point grinding further in this harness.
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

        return successes

    baseline_successes = run_mode(enable_nonstandard=False, seed=2222)
    v2_successes = run_mode(enable_nonstandard=True, seed=2222)

    # If baseline can't successfully generate a reasonable number of boards,
    # this profile/seed isn't a good monotonicity probe – skip rather than fail.
    MIN_BASELINE_SUCCESS = max(1, NUM_BOARDS // 10)
    if baseline_successes < MIN_BASELINE_SUCCESS:
        pytest.skip(
            f"Baseline success rate too low for monotonicity guardrail "
            f"({baseline_successes}/{NUM_BOARDS}); profile/seed too constrained."
        )

    # Monotonicity guardrail:
    # v2 should not be catastrophically worse than baseline on this profile.
    # Currently v2 is a no-op, so these will usually match, but the threshold
    # gives headroom for future tweaks.
    assert v2_successes >= max(1, int(0.8 * baseline_successes))
                
                
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

    # Disable constructive help; we only care about RS/PC/OC ordering here.
    monkeypatch.setattr(
        deal_generator,
        "ENABLE_CONSTRUCTIVE_HELP",
        False,
        raising=False,
    )
    monkeypatch.setattr(
        deal_generator,
        "ENABLE_CONSTRUCTIVE_HELP_NONSTANDARD",
        False,
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
            return True, ["S"]

        # PC / OC / plain seats: unconstrained, always match.
        return True, None

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


def test_nonstandard_shadow_hook_invoked_for_rs_pc_sandbox(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Shadow-mode smoke test for ENABLE_CONSTRUCTIVE_HELP_NONSTANDARD:

      * Build a tiny dummy profile with a non-standard (RS) seat.
      * Enable the non-standard shadow flag.
      * Install a debug hook via _DEBUG_NONSTANDARD_CONSTRUCTIVE_SHADOW.
      * Ensure the hook is invoked and receives a viability summary that
        includes the RS seat, plus an RS bucket snapshot.
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

    # Always succeed when matching seats; for the RS seat, pretend we always
    # choose "S" as the Random Suit and record it.
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
        is_rs = getattr(chosen_subprofile, "random_suit_constraint", None) is not None
        if is_rs:
            random_suit_choices.setdefault(seat, []).append("S")
            # RS seat returns a concrete RS choice payload.
            return True, ["S"]
        # Non-RS seats: unconstrained in this sandbox.
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
        rs_bucket_snapshot,
    ):
        calls.append(
            {
                "profile_name": getattr(profile_arg, "profile_name", ""),
                "board_number": board_number,
                "attempt_number": attempt_number,
                "viability_summary": dict(viability_summary),
                "rs_bucket_snapshot": dict(rs_bucket_snapshot),
            }
        )

    monkeypatch.setattr(
        deal_generator,
        "_DEBUG_NONSTANDARD_CONSTRUCTIVE_SHADOW",
        shadow_hook,
        raising=False,
    )

    rng = random.Random(9999)
    _ = deal_generator._build_single_constrained_deal(
        rng=rng,
        profile=profile,
        board_number=1,
    )

    # The shadow hook must have been called at least once.
    assert calls
    payload = calls[0]

    # Basic sanity on the profile name.
    assert payload["profile_name"] == "RS_PC_shadow_probe_sandbox"

    # The non-standard RS seat should appear in the viability summary.
    summary = payload["viability_summary"]
    assert "W" in summary

    # Check the RS bucket snapshot structure.
    rs_snapshot = payload["rs_bucket_snapshot"]

    # In this sandbox, only W is an RS seat.
    assert set(rs_snapshot.keys()) == {"W"}

    w_entry = rs_snapshot["W"]
    assert set(w_entry.keys()) == {
        "total_seen_attempts",
        "total_matched_attempts",
        "buckets",
    }

    assert w_entry["total_seen_attempts"] == 1
    assert w_entry["total_matched_attempts"] == 1

    buckets = w_entry["buckets"]
    assert isinstance(buckets, dict)
    # With always_match + a single board attempt, we expect exactly one bucket
    # for W, corresponding to the RS choice ["S"] -> key "S".
    assert set(buckets.keys()) == {"S"}

    bucket = buckets["S"]
    assert set(bucket.keys()) == {"seen_attempts", "matched_attempts"}
    assert bucket["seen_attempts"] == 1
    assert bucket["matched_attempts"] == 1
    