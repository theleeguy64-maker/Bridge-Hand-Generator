# tests/test_bespoke_matching.py
#
# Tests for Phase B: Bespoke subprofile matching.
# Verifies ns_bespoke_map / ew_bespoke_map on HandProfile:
#
# Coverage areas:
#   1. Serialization: to_dict / from_dict roundtrip, JSON file roundtrip
#   2. Validation: all error cases in _validate_bespoke_map()
#   3. Validation: valid maps pass without error
#   4. Runtime: _try_pair_coupling() with bespoke_map param (direct)
#   5. Runtime: _select_subprofiles_for_board() integration
#   6. Runtime: combined role filtering + bespoke map
#   7. End-to-end: _build_single_constrained_deal_v2()
#   8. Backwards compatibility: profiles without bespoke maps

from __future__ import annotations

import json
import random
import tempfile
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional

import pytest

from tests.conftest import _standard_all_open  # type: ignore

from bridge_engine.hand_profile_model import (
    HandProfile,
    ProfileError,
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


# ---------------------------------------------------------------------------
# Helper: build a bespoke-map profile
# ---------------------------------------------------------------------------


def _make_bespoke_profile(
    ns_role_mode: str = "north_drives",
    ns_bespoke_map: Optional[Dict[int, List[int]]] = None,
    ew_role_mode: str = "no_driver_no_index",
    ew_bespoke_map: Optional[Dict[int, List[int]]] = None,
    num_n_subs: int = 2,
    num_s_subs: int = 2,
    num_e_subs: int = 1,
    num_w_subs: int = 1,
    n_role_usages: Optional[List[str]] = None,
    s_role_usages: Optional[List[str]] = None,
    e_role_usages: Optional[List[str]] = None,
    w_role_usages: Optional[List[str]] = None,
) -> HandProfile:
    """Build a profile with bespoke map. Flexible helper for many test shapes."""
    std = _standard_all_open()

    def _make_subs(
        count: int, pair_field: str, role_usages: Optional[List[str]]
    ) -> List[SubProfile]:
        weight = 100.0 / count
        subs = []
        for i in range(count):
            kwargs: dict = {"standard": std, "weight_percent": weight}
            if role_usages and i < len(role_usages):
                kwargs[pair_field] = role_usages[i]
            subs.append(SubProfile(**kwargs))
        return subs

    seat_profiles: Dict[str, SeatProfile] = {}
    if num_n_subs > 0:
        seat_profiles["N"] = SeatProfile(
            seat="N", subprofiles=_make_subs(num_n_subs, "ns_role_usage", n_role_usages)
        )
    if num_s_subs > 0:
        seat_profiles["S"] = SeatProfile(
            seat="S", subprofiles=_make_subs(num_s_subs, "ns_role_usage", s_role_usages)
        )
    if num_e_subs > 0:
        seat_profiles["E"] = SeatProfile(
            seat="E", subprofiles=_make_subs(num_e_subs, "ew_role_usage", e_role_usages)
        )
    if num_w_subs > 0:
        seat_profiles["W"] = SeatProfile(
            seat="W", subprofiles=_make_subs(num_w_subs, "ew_role_usage", w_role_usages)
        )

    return HandProfile(
        profile_name="TEST_BESPOKE",
        description="Bespoke matching test",
        dealer="N",
        tag="Opener",
        hand_dealing_order=["N", "S", "E", "W"],
        seat_profiles=seat_profiles,
        ns_role_mode=ns_role_mode,
        ns_bespoke_map=ns_bespoke_map,
        ew_role_mode=ew_role_mode,
        ew_bespoke_map=ew_bespoke_map,
    )


# ===========================================================================
# 1. Serialization tests
# ===========================================================================


def test_bespoke_map_to_dict_from_dict_roundtrip():
    """to_dict → from_dict preserves bespoke map with int keys."""
    bmap = {0: [1, 2], 1: [0]}
    profile = _make_bespoke_profile(
        ns_bespoke_map=bmap,
        num_n_subs=2,
        num_s_subs=3,
    )
    d = profile.to_dict()
    # JSON serialization uses string keys.
    assert d["ns_bespoke_map"] == {"0": [1, 2], "1": [0]}

    # Roundtrip through from_dict.
    restored = HandProfile.from_dict(d)
    assert restored.ns_bespoke_map == {0: [1, 2], 1: [0]}


def test_bespoke_map_none_not_in_dict():
    """When bespoke map is None, it should not appear in to_dict output."""
    profile = _make_bespoke_profile(ns_bespoke_map=None)
    d = profile.to_dict()
    assert "ns_bespoke_map" not in d
    assert "ew_bespoke_map" not in d


def test_ew_bespoke_map_roundtrip():
    """EW bespoke map serializes and deserializes correctly."""
    ew_map = {0: [0, 1], 1: [1]}
    profile = _make_bespoke_profile(
        ew_role_mode="east_drives",
        ew_bespoke_map=ew_map,
        num_e_subs=2,
        num_w_subs=2,
    )
    d = profile.to_dict()
    assert d["ew_bespoke_map"] == {"0": [0, 1], "1": [1]}
    restored = HandProfile.from_dict(d)
    assert restored.ew_bespoke_map == {0: [0, 1], 1: [1]}


def test_both_ns_and_ew_bespoke_map_roundtrip():
    """Both NS and EW bespoke maps survive roundtrip simultaneously."""
    ns_map = {0: [0], 1: [1]}
    ew_map = {0: [0, 1], 1: [0]}
    profile = _make_bespoke_profile(
        ns_bespoke_map=ns_map,
        ew_role_mode="east_drives",
        ew_bespoke_map=ew_map,
        num_e_subs=2,
        num_w_subs=2,
    )
    d = profile.to_dict()
    restored = HandProfile.from_dict(d)
    assert restored.ns_bespoke_map == ns_map
    assert restored.ew_bespoke_map == ew_map


def test_bespoke_map_json_file_roundtrip():
    """Full JSON file write → read → validate roundtrip."""
    bmap = {0: [0, 1], 1: [0], 2: [1]}
    profile = _make_bespoke_profile(
        ns_bespoke_map=bmap,
        num_n_subs=3,
        num_s_subs=2,
    )
    with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
        json.dump(profile.to_dict(), f)
        path = Path(f.name)

    try:
        with open(path) as f:
            raw = json.load(f)
        restored = HandProfile.from_dict(raw)
        assert restored.ns_bespoke_map == bmap
        # Should pass validation.
        validated = validate_profile(restored)
        assert validated.ns_bespoke_map == bmap
    finally:
        path.unlink()


def test_from_dict_missing_bespoke_map_defaults_none():
    """Legacy profile JSON without bespoke map fields → None."""
    profile = _make_bespoke_profile()
    d = profile.to_dict()
    # Manually remove to simulate legacy JSON.
    d.pop("ns_bespoke_map", None)
    d.pop("ew_bespoke_map", None)
    restored = HandProfile.from_dict(d)
    assert restored.ns_bespoke_map is None
    assert restored.ew_bespoke_map is None


# ===========================================================================
# 2. Validation: error cases
# ===========================================================================


def test_validate_bespoke_missing_driver_key():
    """Validation rejects map where a driver sub index is missing as a key."""
    profile = _make_bespoke_profile(
        ns_bespoke_map={0: [0, 1]},  # Missing key 1
        num_n_subs=2,
        num_s_subs=2,
    )
    with pytest.raises(ProfileError, match="driver sub index 1 is missing"):
        validate_profile(profile)


def test_validate_bespoke_missing_follower_sub():
    """Validation rejects map where a follower sub index is unreachable."""
    profile = _make_bespoke_profile(
        ns_bespoke_map={0: [0], 1: [1]},  # Follower sub 2 never appears
        num_n_subs=2,
        num_s_subs=3,
    )
    with pytest.raises(ProfileError, match="follower sub index 2 does not appear"):
        validate_profile(profile)


def test_validate_bespoke_follower_index_out_of_bounds():
    """Validation rejects follower index that exceeds subprofile count."""
    profile = _make_bespoke_profile(
        ns_bespoke_map={0: [0, 5], 1: [0]},  # Index 5 out of bounds
        num_n_subs=2,
        num_s_subs=2,
    )
    with pytest.raises(ProfileError, match="follower index 5.*out of bounds"):
        validate_profile(profile)


def test_validate_bespoke_driver_index_out_of_bounds():
    """Validation rejects driver index key that exceeds subprofile count."""
    profile = _make_bespoke_profile(
        ns_bespoke_map={0: [0], 1: [0], 5: [0]},  # Key 5 out of bounds
        num_n_subs=2,
        num_s_subs=2,
    )
    with pytest.raises(ProfileError, match="driver index 5 out of bounds"):
        validate_profile(profile)


def test_validate_bespoke_negative_follower_index():
    """Validation rejects negative follower index."""
    profile = _make_bespoke_profile(
        ns_bespoke_map={0: [-1], 1: [0]},  # Negative index
        num_n_subs=2,
        num_s_subs=2,
    )
    with pytest.raises(ProfileError, match="follower index -1.*out of bounds"):
        validate_profile(profile)


def test_validate_bespoke_rejected_with_no_driver_no_index():
    """Bespoke map is rejected when role_mode is no_driver_no_index."""
    profile = _make_bespoke_profile(
        ns_role_mode="no_driver_no_index",
        ns_bespoke_map={0: [0], 1: [1]},
        num_n_subs=2,
        num_s_subs=2,
    )
    with pytest.raises(ProfileError, match="not compatible with.*no_driver_no_index"):
        validate_profile(profile)


def test_validate_bespoke_rejected_with_random_driver():
    """Bespoke map is rejected when role_mode is random_driver."""
    profile = _make_bespoke_profile(
        ns_role_mode="random_driver",
        ns_bespoke_map={0: [0], 1: [1]},
        num_n_subs=2,
        num_s_subs=2,
    )
    with pytest.raises(ProfileError, match="not compatible with.*random_driver"):
        validate_profile(profile)


def test_validate_bespoke_empty_value_list():
    """Validation rejects an empty follower candidate list."""
    profile = _make_bespoke_profile(
        ns_bespoke_map={0: [], 1: [0, 1]},  # Key 0 has empty list
        num_n_subs=2,
        num_s_subs=2,
    )
    with pytest.raises(ProfileError, match="driver key 0 has an empty"):
        validate_profile(profile)


def test_validate_ew_bespoke_rejected_with_random_driver():
    """EW bespoke map is rejected when ew_role_mode is random_driver."""
    profile = _make_bespoke_profile(
        ew_role_mode="random_driver",
        ew_bespoke_map={0: [0], 1: [1]},
        num_e_subs=2,
        num_w_subs=2,
    )
    with pytest.raises(ProfileError, match="EW bespoke map is not compatible with.*random_driver"):
        validate_profile(profile)


# ===========================================================================
# 3. Validation: valid maps pass
# ===========================================================================


def test_validate_bespoke_valid_identity_map():
    """A simple identity map {0: [0], 1: [1]} passes validation."""
    profile = _make_bespoke_profile(
        ns_bespoke_map={0: [0], 1: [1]},
        num_n_subs=2,
        num_s_subs=2,
    )
    validated = validate_profile(profile)
    assert validated.ns_bespoke_map == {0: [0], 1: [1]}


def test_validate_bespoke_valid_many_to_many():
    """A map where each driver maps to all followers passes."""
    profile = _make_bespoke_profile(
        ns_bespoke_map={0: [0, 1, 2], 1: [0, 1, 2]},
        num_n_subs=2,
        num_s_subs=3,
    )
    validated = validate_profile(profile)
    assert validated.ns_bespoke_map is not None


def test_validate_bespoke_valid_unequal_counts():
    """Unequal subprofile counts with exhaustive map passes validation."""
    profile = _make_bespoke_profile(
        ns_bespoke_map={0: [0], 1: [0, 1], 2: [1]},
        num_n_subs=3,
        num_s_subs=2,
    )
    validated = validate_profile(profile)
    assert validated.ns_bespoke_map is not None


def test_validate_bespoke_valid_with_south_drives():
    """Bespoke map with south_drives validates correctly (S is driver)."""
    profile = _make_bespoke_profile(
        ns_role_mode="south_drives",
        # With south_drives, S is driver (has 3 subs), N is follower (has 2 subs).
        ns_bespoke_map={0: [0], 1: [0, 1], 2: [1]},
        num_n_subs=2,
        num_s_subs=3,
    )
    validated = validate_profile(profile)
    assert validated.ns_bespoke_map is not None


def test_validate_ew_bespoke_valid_east_drives():
    """EW bespoke map with east_drives passes validation."""
    profile = _make_bespoke_profile(
        ew_role_mode="east_drives",
        ew_bespoke_map={0: [0, 1], 1: [0, 1]},
        num_e_subs=2,
        num_w_subs=2,
    )
    validated = validate_profile(profile)
    assert validated.ew_bespoke_map is not None


def test_validate_ew_bespoke_valid_west_drives():
    """EW bespoke map with west_drives passes validation."""
    profile = _make_bespoke_profile(
        ew_role_mode="west_drives",
        # W is driver (2 subs), E is follower (3 subs).
        ew_bespoke_map={0: [0, 1], 1: [1, 2]},
        num_e_subs=3,
        num_w_subs=2,
    )
    validated = validate_profile(profile)
    assert validated.ew_bespoke_map is not None


# ===========================================================================
# 4. Runtime: _try_pair_coupling() direct tests
# ===========================================================================


def test_try_pair_coupling_bespoke_constrains_follower():
    """_try_pair_coupling with bespoke_map constrains follower to map entries."""
    std = _standard_all_open()
    seat_profiles = {
        "N": SeatProfile(
            seat="N",
            subprofiles=[
                SubProfile(standard=std, weight_percent=100.0),
                SubProfile(standard=std, weight_percent=0.0),
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
    bmap = {0: [1, 2], 1: [0]}  # N picks 0 (100% weight) → S must be 1 or 2.
    rng = random.Random(42)

    for _ in range(100):
        chosen_subs: dict[Seat, SubProfile] = {}
        chosen_idx: dict[Seat, int] = {}
        _try_pair_coupling(
            rng, seat_profiles, "N", "S", "N",
            chosen_subs, chosen_idx, pair="ns", bespoke_map=bmap,
        )
        assert chosen_idx["N"] == 0
        assert chosen_idx["S"] in (1, 2), f"S should be 1 or 2, got {chosen_idx['S']}"


def test_try_pair_coupling_bespoke_unequal_counts():
    """Bespoke map allows unequal subprofile counts in _try_pair_coupling."""
    std = _standard_all_open()
    seat_profiles = {
        "N": SeatProfile(
            seat="N",
            subprofiles=[
                SubProfile(standard=std, weight_percent=34.0),
                SubProfile(standard=std, weight_percent=33.0),
                SubProfile(standard=std, weight_percent=33.0),
            ],
        ),
        "S": SeatProfile(
            seat="S",
            subprofiles=[
                SubProfile(standard=std, weight_percent=50.0),
                SubProfile(standard=std, weight_percent=50.0),
            ],
        ),
    }
    bmap = {0: [0], 1: [0, 1], 2: [1]}
    rng = random.Random(42)

    n_counter: Counter[int] = Counter()
    s_counter: Counter[int] = Counter()
    for _ in range(300):
        chosen_subs: dict[Seat, SubProfile] = {}
        chosen_idx: dict[Seat, int] = {}
        _try_pair_coupling(
            rng, seat_profiles, "N", "S", "N",
            chosen_subs, chosen_idx, pair="ns", bespoke_map=bmap,
        )
        n_counter[chosen_idx["N"]] += 1
        s_counter[chosen_idx["S"]] += 1

    # All 3 driver indices and both follower indices should appear.
    assert set(n_counter.keys()) == {0, 1, 2}
    assert set(s_counter.keys()) == {0, 1}


def test_try_pair_coupling_bespoke_single_follower():
    """When bespoke map gives a single follower candidate, it's always chosen."""
    std = _standard_all_open()
    seat_profiles = {
        "N": SeatProfile(
            seat="N",
            subprofiles=[
                SubProfile(standard=std, weight_percent=100.0),
                SubProfile(standard=std, weight_percent=0.0),
            ],
        ),
        "S": SeatProfile(
            seat="S",
            subprofiles=[
                SubProfile(standard=std, weight_percent=50.0),
                SubProfile(standard=std, weight_percent=50.0),
            ],
        ),
    }
    bmap = {0: [1], 1: [0]}  # N picks 0 → S must be exactly 1.
    rng = random.Random(42)

    for _ in range(50):
        chosen_subs: dict[Seat, SubProfile] = {}
        chosen_idx: dict[Seat, int] = {}
        _try_pair_coupling(
            rng, seat_profiles, "N", "S", "N",
            chosen_subs, chosen_idx, pair="ns", bespoke_map=bmap,
        )
        assert chosen_idx["S"] == 1


def test_try_pair_coupling_bespoke_none_uses_index_coupling():
    """With bespoke_map=None, _try_pair_coupling uses standard index coupling."""
    std = _standard_all_open()
    seat_profiles = {
        "N": SeatProfile(
            seat="N",
            subprofiles=[
                SubProfile(standard=std, weight_percent=100.0),
                SubProfile(standard=std, weight_percent=0.0),
            ],
        ),
        "S": SeatProfile(
            seat="S",
            subprofiles=[
                SubProfile(standard=std, weight_percent=50.0),
                SubProfile(standard=std, weight_percent=50.0),
            ],
        ),
    }
    rng = random.Random(42)

    for _ in range(50):
        chosen_subs: dict[Seat, SubProfile] = {}
        chosen_idx: dict[Seat, int] = {}
        _try_pair_coupling(
            rng, seat_profiles, "N", "S", "N",
            chosen_subs, chosen_idx, pair="ns", bespoke_map=None,
        )
        # N picks 0 (100% weight), S gets same index.
        assert chosen_idx["N"] == 0
        assert chosen_idx["S"] == 0


# ===========================================================================
# 5. Runtime: _select_subprofiles_for_board() integration
# ===========================================================================


def test_runtime_follower_constrained_to_map_entries():
    """
    Over many boards, the follower (S) should only get indices that
    appear in the bespoke map for the chosen driver (N) index.
    """
    std = _standard_all_open()
    profile = HandProfile(
        profile_name="TEST_BESPOKE_RUNTIME",
        description="Bespoke runtime test",
        dealer="N",
        tag="Opener",
        hand_dealing_order=["N", "S", "E", "W"],
        seat_profiles={
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
        },
        ns_role_mode="north_drives",
        ns_bespoke_map={0: [0, 1], 1: [2]},
    )
    validated = validate_profile(profile)

    rng = random.Random(42)
    for _ in range(200):
        _subs, idxs = _select_subprofiles_for_board(rng, validated, ["N", "S", "E", "W"])
        n_idx = idxs["N"]
        s_idx = idxs["S"]
        if n_idx == 0:
            assert s_idx in (0, 1), f"N=0, S should be 0 or 1, got {s_idx}"
        elif n_idx == 1:
            assert s_idx == 2, f"N=1, S should be 2, got {s_idx}"


def test_runtime_unequal_subprofile_counts():
    """Bespoke maps allow unequal subprofile counts (3 driver, 2 follower)."""
    std = _standard_all_open()
    profile = HandProfile(
        profile_name="TEST_BESPOKE_UNEQUAL",
        description="Unequal subprofile counts with bespoke",
        dealer="N",
        tag="Opener",
        hand_dealing_order=["N", "S", "E", "W"],
        seat_profiles={
            "N": SeatProfile(
                seat="N",
                subprofiles=[
                    SubProfile(standard=std, weight_percent=34.0),
                    SubProfile(standard=std, weight_percent=33.0),
                    SubProfile(standard=std, weight_percent=33.0),
                ],
            ),
            "S": SeatProfile(
                seat="S",
                subprofiles=[
                    SubProfile(standard=std, weight_percent=50.0),
                    SubProfile(standard=std, weight_percent=50.0),
                ],
            ),
        },
        ns_role_mode="north_drives",
        ns_bespoke_map={0: [0], 1: [0, 1], 2: [1]},
    )
    validated = validate_profile(profile)

    rng = random.Random(99)
    n_counter: Counter[int] = Counter()
    s_counter: Counter[int] = Counter()
    for _ in range(300):
        _subs, idxs = _select_subprofiles_for_board(rng, validated, ["N", "S", "E", "W"])
        n_counter[idxs["N"]] += 1
        s_counter[idxs["S"]] += 1

    assert set(n_counter.keys()) == {0, 1, 2}
    assert set(s_counter.keys()) == {0, 1}


def test_runtime_south_drives_bespoke():
    """With south_drives + bespoke map, S is driver and map is respected."""
    std = _standard_all_open()
    profile = HandProfile(
        profile_name="TEST_BESPOKE_SOUTH",
        description="south_drives bespoke test",
        dealer="N",
        tag="Opener",
        hand_dealing_order=["N", "S", "E", "W"],
        seat_profiles={
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
                    SubProfile(standard=std, weight_percent=100.0),
                    SubProfile(standard=std, weight_percent=0.0),
                ],
            ),
        },
        ns_role_mode="south_drives",
        # S is driver: sub 0 → N can be [0], sub 1 → N can be [1].
        ns_bespoke_map={0: [0], 1: [1]},
    )
    validated = validate_profile(profile)

    rng = random.Random(42)
    for _ in range(100):
        _subs, idxs = _select_subprofiles_for_board(rng, validated, ["N", "S", "E", "W"])
        # S always picks 0 (100% weight) → N must be 0 per map.
        assert idxs["S"] == 0
        assert idxs["N"] == 0


def test_runtime_ew_bespoke_east_drives():
    """EW bespoke map with east_drives constrains W correctly."""
    std = _standard_all_open()
    profile = HandProfile(
        profile_name="TEST_EW_BESPOKE",
        description="EW bespoke test",
        dealer="N",
        tag="Opener",
        hand_dealing_order=["N", "E", "S", "W"],
        seat_profiles={
            "E": SeatProfile(
                seat="E",
                subprofiles=[
                    SubProfile(standard=std, weight_percent=100.0),
                    SubProfile(standard=std, weight_percent=0.0),
                ],
            ),
            "W": SeatProfile(
                seat="W",
                subprofiles=[
                    SubProfile(standard=std, weight_percent=34.0),
                    SubProfile(standard=std, weight_percent=33.0),
                    SubProfile(standard=std, weight_percent=33.0),
                ],
            ),
        },
        ew_role_mode="east_drives",
        ew_bespoke_map={0: [1, 2], 1: [0]},
    )
    validated = validate_profile(profile)

    rng = random.Random(42)
    for _ in range(100):
        _subs, idxs = _select_subprofiles_for_board(rng, validated, ["N", "E", "S", "W"])
        # E always picks 0 → W must be 1 or 2.
        assert idxs["E"] == 0
        assert idxs["W"] in (1, 2)


def test_runtime_follower_weights_respected_in_bespoke():
    """Within bespoke candidates, follower weights should affect selection."""
    std = _standard_all_open()
    profile = HandProfile(
        profile_name="TEST_BESPOKE_WEIGHTS",
        description="Follower weights within bespoke candidates",
        dealer="N",
        tag="Opener",
        hand_dealing_order=["N", "S", "E", "W"],
        seat_profiles={
            "N": SeatProfile(
                seat="N",
                subprofiles=[
                    SubProfile(standard=std, weight_percent=100.0),
                    SubProfile(standard=std, weight_percent=0.0),
                ],
            ),
            "S": SeatProfile(
                seat="S",
                subprofiles=[
                    SubProfile(standard=std, weight_percent=90.0),  # Heavy
                    SubProfile(standard=std, weight_percent=5.0),   # Light
                    SubProfile(standard=std, weight_percent=5.0),   # Light
                ],
            ),
        },
        ns_role_mode="north_drives",
        ns_bespoke_map={0: [0, 1], 1: [2]},
    )
    validated = validate_profile(profile)

    rng = random.Random(42)
    s_counter: Counter[int] = Counter()
    for _ in range(2000):
        _subs, idxs = _select_subprofiles_for_board(rng, validated, ["N", "S", "E", "W"])
        s_counter[idxs["S"]] += 1

    # N always picks 0 → S candidates are [0, 1].
    # S sub 0 has weight 90, sub 1 has weight 5 → sub 0 should dominate.
    assert 2 not in s_counter, "S sub 2 should never be chosen"
    assert s_counter[0] > s_counter[1] * 5, f"Expected sub 0 >> sub 1, got {s_counter}"


def test_none_map_uses_standard_index_coupling():
    """When bespoke map is None, standard index coupling should work (same index)."""
    std = _standard_all_open()
    profile = HandProfile(
        profile_name="TEST_NO_BESPOKE",
        description="Standard coupling (no bespoke map)",
        dealer="N",
        tag="Opener",
        hand_dealing_order=["N", "S", "E", "W"],
        seat_profiles={
            "N": SeatProfile(
                seat="N",
                subprofiles=[
                    SubProfile(standard=std, weight_percent=100.0),
                    SubProfile(standard=std, weight_percent=0.0),
                ],
            ),
            "S": SeatProfile(
                seat="S",
                subprofiles=[
                    SubProfile(standard=std, weight_percent=50.0),
                    SubProfile(standard=std, weight_percent=50.0),
                ],
            ),
        },
        ns_role_mode="north_drives",
        ns_bespoke_map=None,
    )
    validated = validate_profile(profile)

    rng = random.Random(42)
    for _ in range(100):
        _subs, idxs = _select_subprofiles_for_board(rng, validated, ["N", "S", "E", "W"])
        assert idxs["N"] == 0
        assert idxs["S"] == 0


# ===========================================================================
# 6. Runtime: combined role filtering + bespoke map
# ===========================================================================


def test_runtime_role_filtering_plus_bespoke():
    """Role filtering and bespoke matching combined."""
    std = _standard_all_open()
    profile = HandProfile(
        profile_name="TEST_BESPOKE_ROLE_COMBO",
        description="Combined role filtering + bespoke",
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
        ns_bespoke_map={0: [0], 1: [1]},
    )
    validated = validate_profile(profile)

    rng = random.Random(42)
    for _ in range(100):
        _subs, idxs = _select_subprofiles_for_board(rng, validated, ["N", "S", "E", "W"])
        if idxs["N"] == 0:
            assert idxs["S"] == 0
        else:
            assert idxs["S"] == 1


def test_runtime_bespoke_follower_role_filtering():
    """
    Bespoke map + follower role filtering combined.

    Map says driver 0 → follower [0, 1, 2], but follower sub 0 is driver_only,
    so follower role filter removes it, leaving [1, 2].
    """
    std = _standard_all_open()
    profile = HandProfile(
        profile_name="TEST_BESPOKE_FOLLOWER_FILTER",
        description="Bespoke + follower role filtering",
        dealer="N",
        tag="Opener",
        hand_dealing_order=["N", "S", "E", "W"],
        seat_profiles={
            "N": SeatProfile(
                seat="N",
                subprofiles=[
                    SubProfile(standard=std, weight_percent=100.0),
                    SubProfile(standard=std, weight_percent=0.0),
                ],
            ),
            "S": SeatProfile(
                seat="S",
                subprofiles=[
                    SubProfile(standard=std, ns_role_usage="driver_only", weight_percent=34.0),
                    SubProfile(standard=std, ns_role_usage="any", weight_percent=33.0),
                    SubProfile(standard=std, ns_role_usage="follower_only", weight_percent=33.0),
                ],
            ),
        },
        ns_role_mode="north_drives",
        # Map: driver 0 → [0, 1, 2], driver 1 → [0, 1, 2]
        ns_bespoke_map={0: [0, 1, 2], 1: [0, 1, 2]},
    )
    validated = validate_profile(profile)

    rng = random.Random(42)
    s_counter: Counter[int] = Counter()
    for _ in range(500):
        _subs, idxs = _select_subprofiles_for_board(rng, validated, ["N", "S", "E", "W"])
        s_counter[idxs["S"]] += 1

    # S sub 0 is driver_only → not eligible as follower → should never appear.
    assert s_counter[0] == 0, f"S sub 0 (driver_only) should never be chosen as follower, got {s_counter[0]}"
    # S subs 1 and 2 should both appear.
    assert s_counter[1] > 0
    assert s_counter[2] > 0


# ===========================================================================
# 7. End-to-end: _build_single_constrained_deal_v2()
# ===========================================================================


def test_e2e_bespoke_produces_valid_deals():
    """
    End-to-end: a profile with bespoke map should produce valid deals
    through the full v2 builder pipeline.
    """
    std = _standard_all_open()
    profile = HandProfile(
        profile_name="TEST_E2E_BESPOKE",
        description="E2E bespoke test",
        dealer="N",
        tag="Opener",
        hand_dealing_order=["N", "S", "E", "W"],
        seat_profiles={
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
        },
        ns_role_mode="north_drives",
        ns_bespoke_map={0: [0, 1], 1: [1, 2]},
    )
    validated = validate_profile(profile)
    rng = random.Random(42)

    for board in range(1, 11):
        deal = _build_single_constrained_deal_v2(rng, validated, board_number=board)
        assert deal is not None
        for seat in ("N", "E", "S", "W"):
            assert len(deal.hands[seat]) == 13


def test_e2e_bespoke_unequal_counts():
    """E2E with bespoke map + unequal subprofile counts produces valid deals."""
    std = _standard_all_open()
    profile = HandProfile(
        profile_name="TEST_E2E_BESPOKE_UNEQUAL",
        description="E2E bespoke unequal counts",
        dealer="N",
        tag="Opener",
        hand_dealing_order=["N", "S", "E", "W"],
        seat_profiles={
            "N": SeatProfile(
                seat="N",
                subprofiles=[
                    SubProfile(standard=std, weight_percent=34.0),
                    SubProfile(standard=std, weight_percent=33.0),
                    SubProfile(standard=std, weight_percent=33.0),
                ],
            ),
            "S": SeatProfile(
                seat="S",
                subprofiles=[
                    SubProfile(standard=std, weight_percent=50.0),
                    SubProfile(standard=std, weight_percent=50.0),
                ],
            ),
        },
        ns_role_mode="north_drives",
        ns_bespoke_map={0: [0], 1: [0, 1], 2: [1]},
    )
    validated = validate_profile(profile)
    rng = random.Random(42)

    for board in range(1, 6):
        deal = _build_single_constrained_deal_v2(rng, validated, board_number=board)
        assert deal is not None


# ===========================================================================
# 8. Backwards compatibility
# ===========================================================================


def test_existing_profile_without_bespoke_map_loads():
    """A profile dict without bespoke map fields loads cleanly (None defaults)."""
    std = _standard_all_open()
    profile = HandProfile(
        profile_name="TEST_LEGACY",
        description="Legacy profile without bespoke",
        dealer="N",
        tag="Opener",
        hand_dealing_order=["N", "S", "E", "W"],
        seat_profiles={
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
                    SubProfile(standard=std, weight_percent=50.0),
                    SubProfile(standard=std, weight_percent=50.0),
                ],
            ),
        },
        ns_role_mode="north_drives",
    )
    assert profile.ns_bespoke_map is None
    assert profile.ew_bespoke_map is None

    validated = validate_profile(profile)
    assert validated.ns_bespoke_map is None
    assert validated.ew_bespoke_map is None


def test_existing_profile_index_coupling_still_works():
    """Standard index coupling (no bespoke) still works end-to-end."""
    std = _standard_all_open()
    profile = HandProfile(
        profile_name="TEST_LEGACY_COUPLING",
        description="Legacy index coupling",
        dealer="N",
        tag="Opener",
        hand_dealing_order=["N", "S", "E", "W"],
        seat_profiles={
            "N": SeatProfile(
                seat="N",
                subprofiles=[
                    SubProfile(standard=std, weight_percent=100.0),
                    SubProfile(standard=std, weight_percent=0.0),
                ],
            ),
            "S": SeatProfile(
                seat="S",
                subprofiles=[
                    SubProfile(standard=std, weight_percent=50.0),
                    SubProfile(standard=std, weight_percent=50.0),
                ],
            ),
        },
        ns_role_mode="north_drives",
    )
    validated = validate_profile(profile)
    rng = random.Random(42)

    for _ in range(100):
        _subs, idxs = _select_subprofiles_for_board(rng, validated, ["N", "S", "E", "W"])
        # N always picks 0, S must follow via standard index coupling.
        assert idxs["N"] == 0
        assert idxs["S"] == 0


def test_golden_profiles_load_without_bespoke_errors():
    """
    All existing .json profiles in profiles/ should load without
    bespoke-related validation errors (they have no bespoke maps).
    """
    profiles_dir = Path(__file__).resolve().parent.parent / "profiles"
    if not profiles_dir.exists():
        return  # Skip if profiles dir not present.

    for path in sorted(profiles_dir.glob("*.json")):
        # Skip draft files.
        if "_TEST" in path.stem or "_DRAFT" in path.stem:
            continue
        with open(path) as f:
            raw = json.load(f)
        # Should load and validate without error.
        profile = validate_profile(raw)
        # All existing profiles should have None bespoke maps.
        assert profile.ns_bespoke_map is None, f"{path.name} has unexpected ns_bespoke_map"
        assert profile.ew_bespoke_map is None, f"{path.name} has unexpected ew_bespoke_map"
