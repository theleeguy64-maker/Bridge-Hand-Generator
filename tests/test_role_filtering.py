# tests/test_role_filtering.py
#
# Tests for Phase A: Driver/Follower role filtering at subprofile selection time.
# Verifies that ns_role_usage / ew_role_usage on SubProfile is respected
# when choosing subprofile indices in _try_pair_coupling().
#
# Coverage areas:
#   1. Unit tests for _eligible_indices_for_role() — all pair/role combos
#   2. Unit tests for _choose_index_for_seat() with eligible_indices param
#   3. Direct tests for _try_pair_coupling() with pair param
#   4. Integration tests via _select_subprofiles_for_board()
#   5. End-to-end tests via _build_single_constrained_deal_v2()

from __future__ import annotations

import random
from collections import Counter

from tests.conftest import _standard_all_open  # type: ignore

from bridge_engine.hand_profile_model import (
    HandProfile,
    SeatProfile,
    SubProfile,
)
from bridge_engine.hand_profile_validate import validate_profile
from bridge_engine.deal_generator import (
    _select_subprofiles_for_board,
    _try_pair_coupling,
    _build_single_constrained_deal_v2,
    Seat,
)
from bridge_engine.deal_generator_helpers import (
    _eligible_indices_for_role,
    _choose_index_for_seat,
)


# ---------------------------------------------------------------------------
# 1. Unit tests for _eligible_indices_for_role()
# ---------------------------------------------------------------------------


def test_eligible_indices_ns_driver():
    """NS driver should see 'any' and 'driver_only' subs."""
    std = _standard_all_open()
    sp = SeatProfile(
        seat="N",
        subprofiles=[
            SubProfile(standard=std, ns_role_usage="driver_only", weight_percent=50.0),
            SubProfile(standard=std, ns_role_usage="follower_only", weight_percent=25.0),
            SubProfile(standard=std, ns_role_usage="any", weight_percent=25.0),
        ],
    )
    result = _eligible_indices_for_role(sp, "driver", "ns")
    assert result == [0, 2], f"Expected [0, 2], got {result}"


def test_eligible_indices_ns_follower():
    """NS follower should see 'any' and 'follower_only' subs."""
    std = _standard_all_open()
    sp = SeatProfile(
        seat="S",
        subprofiles=[
            SubProfile(standard=std, ns_role_usage="driver_only", weight_percent=50.0),
            SubProfile(standard=std, ns_role_usage="follower_only", weight_percent=25.0),
            SubProfile(standard=std, ns_role_usage="any", weight_percent=25.0),
        ],
    )
    result = _eligible_indices_for_role(sp, "follower", "ns")
    assert result == [1, 2], f"Expected [1, 2], got {result}"


def test_eligible_indices_ew_driver():
    """EW driver should see 'any' and 'driver_only' subs via ew_role_usage."""
    std = _standard_all_open()
    sp = SeatProfile(
        seat="E",
        subprofiles=[
            SubProfile(standard=std, ew_role_usage="any", weight_percent=50.0),
            SubProfile(standard=std, ew_role_usage="follower_only", weight_percent=50.0),
        ],
    )
    result = _eligible_indices_for_role(sp, "driver", "ew")
    assert result == [0], f"Expected [0], got {result}"


def test_eligible_indices_ew_follower():
    """EW follower should see 'any' and 'follower_only' subs via ew_role_usage."""
    std = _standard_all_open()
    sp = SeatProfile(
        seat="W",
        subprofiles=[
            SubProfile(standard=std, ew_role_usage="driver_only", weight_percent=50.0),
            SubProfile(standard=std, ew_role_usage="any", weight_percent=50.0),
        ],
    )
    result = _eligible_indices_for_role(sp, "follower", "ew")
    assert result == [1], f"Expected [1], got {result}"


def test_eligible_indices_all_any_returns_all():
    """When all subs are 'any', all indices should be eligible for either role."""
    std = _standard_all_open()
    sp = SeatProfile(
        seat="N",
        subprofiles=[
            SubProfile(standard=std, ns_role_usage="any", weight_percent=50.0),
            SubProfile(standard=std, ns_role_usage="any", weight_percent=50.0),
        ],
    )
    assert _eligible_indices_for_role(sp, "driver", "ns") == [0, 1]
    assert _eligible_indices_for_role(sp, "follower", "ns") == [0, 1]


def test_eligible_indices_all_driver_only():
    """When all subs are 'driver_only', follower should fall back to all indices."""
    std = _standard_all_open()
    sp = SeatProfile(
        seat="N",
        subprofiles=[
            SubProfile(standard=std, ns_role_usage="driver_only", weight_percent=50.0),
            SubProfile(standard=std, ns_role_usage="driver_only", weight_percent=50.0),
        ],
    )
    # Driver: both eligible.
    assert _eligible_indices_for_role(sp, "driver", "ns") == [0, 1]
    # Follower: none match "any" or "follower_only" → safety fallback returns all.
    assert _eligible_indices_for_role(sp, "follower", "ns") == [0, 1]


def test_eligible_indices_all_follower_only():
    """When all subs are 'follower_only', driver should fall back to all indices."""
    std = _standard_all_open()
    sp = SeatProfile(
        seat="S",
        subprofiles=[
            SubProfile(standard=std, ns_role_usage="follower_only", weight_percent=50.0),
            SubProfile(standard=std, ns_role_usage="follower_only", weight_percent=50.0),
        ],
    )
    # Driver: none match → safety fallback returns all.
    assert _eligible_indices_for_role(sp, "driver", "ns") == [0, 1]
    # Follower: both eligible.
    assert _eligible_indices_for_role(sp, "follower", "ns") == [0, 1]


def test_eligible_indices_ns_pair_ignores_ew_role_usage():
    """When pair='ns', the ew_role_usage field should be ignored."""
    std = _standard_all_open()
    sp = SeatProfile(
        seat="N",
        subprofiles=[
            SubProfile(
                standard=std,
                ns_role_usage="any",
                ew_role_usage="driver_only",
                weight_percent=50.0,
            ),
            SubProfile(
                standard=std,
                ns_role_usage="driver_only",
                ew_role_usage="follower_only",
                weight_percent=50.0,
            ),
        ],
    )
    # NS driver checks ns_role_usage only: both are driver-eligible.
    assert _eligible_indices_for_role(sp, "driver", "ns") == [0, 1]
    # NS follower: sub 0 is "any" → eligible; sub 1 is "driver_only" → not.
    assert _eligible_indices_for_role(sp, "follower", "ns") == [0]


def test_eligible_indices_ew_pair_ignores_ns_role_usage():
    """When pair='ew', the ns_role_usage field should be ignored."""
    std = _standard_all_open()
    sp = SeatProfile(
        seat="E",
        subprofiles=[
            SubProfile(
                standard=std,
                ns_role_usage="follower_only",
                ew_role_usage="any",
                weight_percent=50.0,
            ),
            SubProfile(
                standard=std,
                ns_role_usage="driver_only",
                ew_role_usage="driver_only",
                weight_percent=50.0,
            ),
        ],
    )
    # EW driver checks ew_role_usage only: both are driver-eligible.
    assert _eligible_indices_for_role(sp, "driver", "ew") == [0, 1]
    # EW follower: sub 0 "any" → eligible; sub 1 "driver_only" → not.
    assert _eligible_indices_for_role(sp, "follower", "ew") == [0]


def test_eligible_indices_single_subprofile():
    """Single-subprofile seat always returns [0] regardless of role_usage."""
    std = _standard_all_open()
    sp = SeatProfile(
        seat="N",
        subprofiles=[
            SubProfile(standard=std, ns_role_usage="driver_only", weight_percent=100.0),
        ],
    )
    # Even as follower, "driver_only" doesn't match, but fallback returns all.
    assert _eligible_indices_for_role(sp, "driver", "ns") == [0]
    assert _eligible_indices_for_role(sp, "follower", "ns") == [0]


# ---------------------------------------------------------------------------
# 2. Unit tests for _choose_index_for_seat() with eligible_indices
# ---------------------------------------------------------------------------


def test_choose_index_with_eligible_indices_subset():
    """_choose_index_for_seat with eligible_indices picks only from the subset."""
    std = _standard_all_open()
    sp = SeatProfile(
        seat="N",
        subprofiles=[
            SubProfile(standard=std, weight_percent=50.0),
            SubProfile(standard=std, weight_percent=25.0),
            SubProfile(standard=std, weight_percent=25.0),
        ],
    )
    rng = random.Random(42)
    # Only allow indices 1 and 2.
    results = {_choose_index_for_seat(rng, sp, eligible_indices=[1, 2]) for _ in range(200)}
    assert results <= {1, 2}, f"Should only pick from [1, 2], got {results}"
    # Both should appear with enough samples.
    assert results == {1, 2}, f"Expected both 1 and 2 to appear, got {results}"


def test_choose_index_with_single_eligible():
    """_choose_index_for_seat with a single eligible index always returns that index."""
    std = _standard_all_open()
    sp = SeatProfile(
        seat="N",
        subprofiles=[
            SubProfile(standard=std, weight_percent=50.0),
            SubProfile(standard=std, weight_percent=50.0),
        ],
    )
    rng = random.Random(42)
    for _ in range(50):
        assert _choose_index_for_seat(rng, sp, eligible_indices=[1]) == 1


def test_choose_index_without_eligible_indices_uses_all():
    """_choose_index_for_seat without eligible_indices picks from all subs."""
    std = _standard_all_open()
    sp = SeatProfile(
        seat="N",
        subprofiles=[
            SubProfile(standard=std, weight_percent=50.0),
            SubProfile(standard=std, weight_percent=50.0),
        ],
    )
    rng = random.Random(42)
    results = {_choose_index_for_seat(rng, sp) for _ in range(200)}
    assert results == {0, 1}


def test_choose_index_single_subprofile_ignores_eligible():
    """A seat with 1 subprofile always returns 0 regardless of eligible_indices."""
    std = _standard_all_open()
    sp = SeatProfile(
        seat="N",
        subprofiles=[SubProfile(standard=std, weight_percent=100.0)],
    )
    rng = random.Random(42)
    # eligible_indices is ignored when there's only 1 sub.
    assert _choose_index_for_seat(rng, sp, eligible_indices=[0]) == 0
    assert _choose_index_for_seat(rng, sp) == 0


def test_choose_index_eligible_weights_respected():
    """Weights within the eligible subset should determine pick frequencies."""
    std = _standard_all_open()
    # Sub 0: weight 90, Sub 1: weight 5, Sub 2: weight 5
    sp = SeatProfile(
        seat="N",
        subprofiles=[
            SubProfile(standard=std, weight_percent=90.0),
            SubProfile(standard=std, weight_percent=5.0),
            SubProfile(standard=std, weight_percent=5.0),
        ],
    )
    rng = random.Random(42)
    # Only eligible: [0, 2]. Sub 0 has weight 90, sub 2 has weight 5.
    counter: Counter[int] = Counter()
    for _ in range(2000):
        counter[_choose_index_for_seat(rng, sp, eligible_indices=[0, 2])] += 1

    assert 1 not in counter, "Index 1 should never be chosen"
    # Sub 0 should dominate (~95% expected).
    assert counter[0] > counter[2] * 5, f"Expected sub 0 >> sub 2, got {counter}"


# ---------------------------------------------------------------------------
# 3. Direct tests for _try_pair_coupling() with pair param
# ---------------------------------------------------------------------------


def test_try_pair_coupling_ns_driver_filters():
    """_try_pair_coupling with pair='ns' applies NS role filtering to driver."""
    std = _standard_all_open()
    seat_profiles = {
        "N": SeatProfile(
            seat="N",
            subprofiles=[
                SubProfile(standard=std, ns_role_usage="follower_only", weight_percent=50.0),
                SubProfile(standard=std, ns_role_usage="driver_only", weight_percent=50.0),
            ],
        ),
        "S": SeatProfile(
            seat="S",
            subprofiles=[
                SubProfile(standard=std, ns_role_usage="any", weight_percent=50.0),
                SubProfile(standard=std, ns_role_usage="any", weight_percent=50.0),
            ],
        ),
    }
    rng = random.Random(42)
    chosen_subs: dict[Seat, SubProfile] = {}
    chosen_idx: dict[Seat, int] = {}

    for _ in range(100):
        chosen_subs.clear()
        chosen_idx.clear()
        _try_pair_coupling(rng, seat_profiles, "N", "S", "N", chosen_subs, chosen_idx, pair="ns")
        # N is driver: sub 0 is follower_only → ineligible. Must pick sub 1.
        assert chosen_idx["N"] == 1, f"N (driver) should always pick 1, got {chosen_idx['N']}"
        # Standard coupling: S gets same index.
        assert chosen_idx["S"] == 1


def test_try_pair_coupling_ew_driver_filters():
    """_try_pair_coupling with pair='ew' applies EW role filtering."""
    std = _standard_all_open()
    seat_profiles = {
        "E": SeatProfile(
            seat="E",
            subprofiles=[
                SubProfile(standard=std, ew_role_usage="driver_only", weight_percent=50.0),
                SubProfile(standard=std, ew_role_usage="follower_only", weight_percent=50.0),
            ],
        ),
        "W": SeatProfile(
            seat="W",
            subprofiles=[
                SubProfile(standard=std, ew_role_usage="any", weight_percent=50.0),
                SubProfile(standard=std, ew_role_usage="any", weight_percent=50.0),
            ],
        ),
    }
    rng = random.Random(42)
    for _ in range(100):
        chosen_subs: dict[Seat, SubProfile] = {}
        chosen_idx: dict[Seat, int] = {}
        _try_pair_coupling(rng, seat_profiles, "E", "W", "E", chosen_subs, chosen_idx, pair="ew")
        # E is driver: sub 0 (driver_only) eligible, sub 1 (follower_only) not.
        assert chosen_idx["E"] == 0
        assert chosen_idx["W"] == 0


def test_try_pair_coupling_no_pair_param_defaults_ns():
    """_try_pair_coupling without explicit pair param defaults to 'ns'."""
    std = _standard_all_open()
    seat_profiles = {
        "N": SeatProfile(
            seat="N",
            subprofiles=[
                SubProfile(standard=std, ns_role_usage="any", weight_percent=50.0),
                SubProfile(standard=std, ns_role_usage="any", weight_percent=50.0),
            ],
        ),
        "S": SeatProfile(
            seat="S",
            subprofiles=[
                SubProfile(standard=std, ns_role_usage="any", weight_percent=50.0),
                SubProfile(standard=std, ns_role_usage="any", weight_percent=50.0),
            ],
        ),
    }
    rng = random.Random(42)
    chosen_subs: dict[Seat, SubProfile] = {}
    chosen_idx: dict[Seat, int] = {}
    # Call without pair — should default to "ns" and work fine.
    _try_pair_coupling(rng, seat_profiles, "N", "S", "N", chosen_subs, chosen_idx)
    assert "N" in chosen_idx
    assert "S" in chosen_idx
    assert chosen_idx["N"] == chosen_idx["S"]


def test_try_pair_coupling_unequal_counts_no_bespoke_skips():
    """Without bespoke map, unequal subprofile counts cause coupling to skip."""
    std = _standard_all_open()
    seat_profiles = {
        "N": SeatProfile(
            seat="N",
            subprofiles=[
                SubProfile(standard=std, weight_percent=50.0),
                SubProfile(standard=std, weight_percent=50.0),
            ],
        ),
        "S": SeatProfile(
            seat="S",
            subprofiles=[
                SubProfile(standard=std, weight_percent=34.0),
                SubProfile(standard=std, weight_percent=33.0),
                SubProfile(standard=std, weight_percent=33.0),
            ],
        ),
    }
    rng = random.Random(42)
    chosen_subs: dict[Seat, SubProfile] = {}
    chosen_idx: dict[Seat, int] = {}
    _try_pair_coupling(rng, seat_profiles, "N", "S", "N", chosen_subs, chosen_idx, pair="ns")
    # Should do nothing (unequal counts, no bespoke).
    assert "N" not in chosen_idx
    assert "S" not in chosen_idx


# ---------------------------------------------------------------------------
# 4. Integration tests: _select_subprofiles_for_board with role filtering
# ---------------------------------------------------------------------------


def test_driver_only_sub_never_chosen_as_follower():
    """
    N has sub 0 = driver_only, sub 1 = follower_only.
    north_drives → N is driver, can only pick driver-eligible sub 0.
    S always gets same index via coupling.
    """
    std = _standard_all_open()
    profile = HandProfile(
        profile_name="TEST_ROLE_FILTER_NS",
        description="Role filtering test",
        dealer="N",
        tag="Opener",
        hand_dealing_order=["N", "S", "E", "W"],
        seat_profiles={
            "N": SeatProfile(
                seat="N",
                subprofiles=[
                    SubProfile(standard=std, ns_role_usage="driver_only", weight_percent=50.0),
                    SubProfile(standard=std, ns_role_usage="follower_only", weight_percent=50.0),
                ],
            ),
            "S": SeatProfile(
                seat="S",
                subprofiles=[
                    SubProfile(standard=std, ns_role_usage="any", weight_percent=50.0),
                    SubProfile(standard=std, ns_role_usage="any", weight_percent=50.0),
                ],
            ),
        },
        ns_role_mode="north_drives",
    )
    validated = validate_profile(profile)

    rng = random.Random(42)
    indices_n: list[int] = []
    for _ in range(100):
        _subs, idxs = _select_subprofiles_for_board(rng, validated, ["N", "S", "E", "W"])
        indices_n.append(idxs["N"])

    assert all(i == 0 for i in indices_n), f"N should always pick index 0, got {Counter(indices_n)}"


def test_follower_only_sub_never_chosen_as_driver():
    """N has sub 0 = follower_only, sub 1 = driver_only. N (driver) always picks sub 1."""
    std = _standard_all_open()
    profile = HandProfile(
        profile_name="TEST_ROLE_FILTER_NS_2",
        description="Follower-only never chosen as driver",
        dealer="N",
        tag="Opener",
        hand_dealing_order=["N", "S", "E", "W"],
        seat_profiles={
            "N": SeatProfile(
                seat="N",
                subprofiles=[
                    SubProfile(standard=std, ns_role_usage="follower_only", weight_percent=50.0),
                    SubProfile(standard=std, ns_role_usage="driver_only", weight_percent=50.0),
                ],
            ),
            "S": SeatProfile(
                seat="S",
                subprofiles=[
                    SubProfile(standard=std, ns_role_usage="any", weight_percent=50.0),
                    SubProfile(standard=std, ns_role_usage="any", weight_percent=50.0),
                ],
            ),
        },
        ns_role_mode="north_drives",
    )
    validated = validate_profile(profile)

    rng = random.Random(99)
    for _ in range(100):
        _subs, idxs = _select_subprofiles_for_board(rng, validated, ["N", "S", "E", "W"])
        assert idxs["N"] == 1, "N as driver should never pick follower_only sub 0"


def test_south_drives_role_filtering():
    """With south_drives, S is driver. S's follower_only subs should be excluded."""
    std = _standard_all_open()
    profile = HandProfile(
        profile_name="TEST_SOUTH_DRIVES",
        description="south_drives role filtering",
        dealer="N",
        tag="Opener",
        hand_dealing_order=["N", "S", "E", "W"],
        seat_profiles={
            "N": SeatProfile(
                seat="N",
                subprofiles=[
                    SubProfile(standard=std, ns_role_usage="any", weight_percent=50.0),
                    SubProfile(standard=std, ns_role_usage="any", weight_percent=50.0),
                ],
            ),
            "S": SeatProfile(
                seat="S",
                subprofiles=[
                    SubProfile(standard=std, ns_role_usage="follower_only", weight_percent=50.0),
                    SubProfile(standard=std, ns_role_usage="driver_only", weight_percent=50.0),
                ],
            ),
        },
        ns_role_mode="south_drives",
    )
    validated = validate_profile(profile)

    rng = random.Random(42)
    for _ in range(100):
        _subs, idxs = _select_subprofiles_for_board(rng, validated, ["N", "S", "E", "W"])
        # S is driver → can only pick sub 1 (driver_only). Sub 0 (follower_only) excluded.
        assert idxs["S"] == 1, f"S (driver) should always pick 1, got {idxs['S']}"
        # N (follower) gets same index via coupling.
        assert idxs["N"] == 1


def test_ew_east_drives_role_filtering():
    """EW coupling with east_drives filters E as driver, W as follower."""
    std = _standard_all_open()
    profile = HandProfile(
        profile_name="TEST_EW_EAST_DRIVES",
        description="EW east_drives role filtering",
        dealer="N",
        tag="Opener",
        hand_dealing_order=["N", "E", "S", "W"],
        seat_profiles={
            "E": SeatProfile(
                seat="E",
                subprofiles=[
                    SubProfile(standard=std, ew_role_usage="driver_only", weight_percent=50.0),
                    SubProfile(standard=std, ew_role_usage="follower_only", weight_percent=50.0),
                ],
            ),
            "W": SeatProfile(
                seat="W",
                subprofiles=[
                    SubProfile(standard=std, ew_role_usage="any", weight_percent=50.0),
                    SubProfile(standard=std, ew_role_usage="any", weight_percent=50.0),
                ],
            ),
        },
        ew_role_mode="east_drives",
    )
    validated = validate_profile(profile)

    rng = random.Random(42)
    for _ in range(100):
        _subs, idxs = _select_subprofiles_for_board(rng, validated, ["N", "E", "S", "W"])
        # E (driver) should always pick sub 0 (driver_only).
        assert idxs["E"] == 0
        assert idxs["W"] == 0


def test_ew_west_drives_role_filtering():
    """EW coupling with west_drives filters W as driver."""
    std = _standard_all_open()
    profile = HandProfile(
        profile_name="TEST_EW_WEST_DRIVES",
        description="EW west_drives role filtering",
        dealer="N",
        tag="Opener",
        hand_dealing_order=["N", "E", "S", "W"],
        seat_profiles={
            "E": SeatProfile(
                seat="E",
                subprofiles=[
                    SubProfile(standard=std, ew_role_usage="any", weight_percent=50.0),
                    SubProfile(standard=std, ew_role_usage="any", weight_percent=50.0),
                ],
            ),
            "W": SeatProfile(
                seat="W",
                subprofiles=[
                    SubProfile(standard=std, ew_role_usage="follower_only", weight_percent=50.0),
                    SubProfile(standard=std, ew_role_usage="driver_only", weight_percent=50.0),
                ],
            ),
        },
        ew_role_mode="west_drives",
    )
    validated = validate_profile(profile)

    rng = random.Random(42)
    for _ in range(100):
        _subs, idxs = _select_subprofiles_for_board(rng, validated, ["N", "E", "S", "W"])
        # W (driver) should always pick sub 1 (driver_only).
        assert idxs["W"] == 1
        assert idxs["E"] == 1


def test_random_driver_filters_per_board():
    """
    With random_driver mode, selection runs without errors over many boards.
    Both N and S should get indices assigned.
    """
    std = _standard_all_open()
    profile = HandProfile(
        profile_name="TEST_RANDOM_DRIVER",
        description="random_driver role filter test",
        dealer="N",
        tag="Opener",
        hand_dealing_order=["N", "S", "E", "W"],
        seat_profiles={
            "N": SeatProfile(
                seat="N",
                subprofiles=[
                    SubProfile(standard=std, ns_role_usage="any", weight_percent=50.0),
                    SubProfile(standard=std, ns_role_usage="any", weight_percent=50.0),
                ],
            ),
            "S": SeatProfile(
                seat="S",
                subprofiles=[
                    SubProfile(standard=std, ns_role_usage="any", weight_percent=50.0),
                    SubProfile(standard=std, ns_role_usage="any", weight_percent=50.0),
                ],
            ),
        },
        ns_role_mode="random_driver",
    )
    validated = validate_profile(profile)

    rng = random.Random(777)
    for _ in range(200):
        _subs, idxs = _select_subprofiles_for_board(rng, validated, ["N", "S", "E", "W"])
        assert "N" in idxs
        assert "S" in idxs


def test_no_driver_no_index_skips_filtering():
    """
    With no_driver_no_index, role filtering is not applied (coupling is off).
    Each seat picks independently — both indices should appear.
    """
    std = _standard_all_open()
    profile = HandProfile(
        profile_name="TEST_NO_DRIVER",
        description="no_driver_no_index skips filtering",
        dealer="N",
        tag="Opener",
        hand_dealing_order=["N", "S", "E", "W"],
        seat_profiles={
            "N": SeatProfile(
                seat="N",
                subprofiles=[
                    SubProfile(standard=std, ns_role_usage="driver_only", weight_percent=50.0),
                    SubProfile(standard=std, ns_role_usage="follower_only", weight_percent=50.0),
                ],
            ),
            "S": SeatProfile(
                seat="S",
                subprofiles=[
                    SubProfile(standard=std, ns_role_usage="any", weight_percent=50.0),
                    SubProfile(standard=std, ns_role_usage="any", weight_percent=50.0),
                ],
            ),
        },
        ns_role_mode="no_driver_no_index",
    )
    validated = validate_profile(profile)

    rng = random.Random(42)
    n_indices: list[int] = []
    for _ in range(200):
        _subs, idxs = _select_subprofiles_for_board(rng, validated, ["N", "S", "E", "W"])
        n_indices.append(idxs["N"])

    unique = set(n_indices)
    assert len(unique) == 2, f"Expected both indices to appear, got {unique}"


def test_weights_respected_among_eligible_subs():
    """Weights within the eligible pool should be respected after role filtering."""
    std = _standard_all_open()
    profile = HandProfile(
        profile_name="TEST_WEIGHTS_FILTER",
        description="Weights respected in filtered pool",
        dealer="N",
        tag="Opener",
        hand_dealing_order=["N", "S", "E", "W"],
        seat_profiles={
            "N": SeatProfile(
                seat="N",
                subprofiles=[
                    SubProfile(standard=std, ns_role_usage="driver_only", weight_percent=45.0),
                    SubProfile(standard=std, ns_role_usage="driver_only", weight_percent=5.0),
                    SubProfile(standard=std, ns_role_usage="follower_only", weight_percent=50.0),
                ],
            ),
            "S": SeatProfile(
                seat="S",
                subprofiles=[
                    SubProfile(standard=std, ns_role_usage="any", weight_percent=34.0),
                    SubProfile(standard=std, ns_role_usage="any", weight_percent=33.0),
                    SubProfile(standard=std, ns_role_usage="any", weight_percent=33.0),
                ],
            ),
        },
        ns_role_mode="north_drives",
    )
    validated = validate_profile(profile)

    rng = random.Random(42)
    counter: Counter[int] = Counter()
    for _ in range(1000):
        _subs, idxs = _select_subprofiles_for_board(rng, validated, ["N", "S", "E", "W"])
        counter[idxs["N"]] += 1

    assert counter[2] == 0, f"follower_only sub should never be chosen as driver, got {counter[2]}"
    assert counter[0] > counter[1] * 3, f"Expected sub 0 >> sub 1, got {counter}"


def test_ns_and_ew_filtering_simultaneously():
    """Both NS and EW filtering active in the same profile."""
    std = _standard_all_open()
    profile = HandProfile(
        profile_name="TEST_BOTH_PAIRS",
        description="Simultaneous NS + EW role filtering",
        dealer="N",
        tag="Opener",
        hand_dealing_order=["N", "E", "S", "W"],
        seat_profiles={
            "N": SeatProfile(
                seat="N",
                subprofiles=[
                    SubProfile(standard=std, ns_role_usage="driver_only", weight_percent=50.0),
                    SubProfile(standard=std, ns_role_usage="follower_only", weight_percent=50.0),
                ],
            ),
            "S": SeatProfile(
                seat="S",
                subprofiles=[
                    SubProfile(standard=std, ns_role_usage="any", weight_percent=50.0),
                    SubProfile(standard=std, ns_role_usage="any", weight_percent=50.0),
                ],
            ),
            "E": SeatProfile(
                seat="E",
                subprofiles=[
                    SubProfile(standard=std, ew_role_usage="follower_only", weight_percent=50.0),
                    SubProfile(standard=std, ew_role_usage="driver_only", weight_percent=50.0),
                ],
            ),
            "W": SeatProfile(
                seat="W",
                subprofiles=[
                    SubProfile(standard=std, ew_role_usage="any", weight_percent=50.0),
                    SubProfile(standard=std, ew_role_usage="any", weight_percent=50.0),
                ],
            ),
        },
        ns_role_mode="north_drives",
        ew_role_mode="east_drives",
    )
    validated = validate_profile(profile)

    rng = random.Random(42)
    for _ in range(100):
        _subs, idxs = _select_subprofiles_for_board(rng, validated, ["N", "E", "S", "W"])
        # N (driver): sub 0 (driver_only) always chosen.
        assert idxs["N"] == 0
        # E (driver): sub 1 (driver_only) always chosen.
        assert idxs["E"] == 1


def test_single_subprofile_seat_bypasses_coupling():
    """A seat with only 1 subprofile always gets index 0, no coupling needed."""
    std = _standard_all_open()
    profile = HandProfile(
        profile_name="TEST_SINGLE_SUB",
        description="Single-sub seat always index 0",
        dealer="N",
        tag="Opener",
        hand_dealing_order=["N", "S", "E", "W"],
        seat_profiles={
            "N": SeatProfile(
                seat="N",
                subprofiles=[SubProfile(standard=std, weight_percent=100.0)],
            ),
            "S": SeatProfile(
                seat="S",
                subprofiles=[SubProfile(standard=std, weight_percent=100.0)],
            ),
        },
        ns_role_mode="north_drives",
    )
    validated = validate_profile(profile)

    rng = random.Random(42)
    for _ in range(50):
        _subs, idxs = _select_subprofiles_for_board(rng, validated, ["N", "S", "E", "W"])
        assert idxs["N"] == 0
        assert idxs["S"] == 0


# ---------------------------------------------------------------------------
# 5. End-to-end test via _build_single_constrained_deal_v2()
# ---------------------------------------------------------------------------


def test_e2e_role_filtering_produces_valid_deal():
    """
    End-to-end: a profile with role filtering should produce valid deals
    through the full v2 builder pipeline.
    """
    std = _standard_all_open()
    profile = HandProfile(
        profile_name="TEST_E2E_ROLE",
        description="E2E role filtering test",
        dealer="N",
        tag="Opener",
        hand_dealing_order=["N", "S", "E", "W"],
        seat_profiles={
            "N": SeatProfile(
                seat="N",
                subprofiles=[
                    SubProfile(standard=std, ns_role_usage="driver_only", weight_percent=50.0),
                    SubProfile(standard=std, ns_role_usage="any", weight_percent=50.0),
                ],
            ),
            "S": SeatProfile(
                seat="S",
                subprofiles=[
                    SubProfile(standard=std, ns_role_usage="any", weight_percent=50.0),
                    SubProfile(standard=std, ns_role_usage="any", weight_percent=50.0),
                ],
            ),
        },
        ns_role_mode="north_drives",
    )
    validated = validate_profile(profile)
    rng = random.Random(42)

    # Generate multiple deals to exercise the pipeline.
    for board in range(1, 6):
        deal = _build_single_constrained_deal_v2(rng, validated, board_number=board)
        assert deal is not None
        # Each hand should have exactly 13 cards.
        for seat in ("N", "E", "S", "W"):
            assert len(deal.hands[seat]) == 13, f"Board {board}, seat {seat} has {len(deal.hands[seat])} cards"
