# tests/test_linked_profiles.py
#
# Tests for the LinkedProfile system — the replacement for driver/role/bespoke
# coupling. Covers:
#
#   1. LinkedProfile dataclass: construction, to_dict/from_dict roundtrip
#   2. HandProfile integration: ns/ew_linked_profile fields, serialization
#   3. Stage 2 logic: _apply_linked_profile(), _select_subprofiles_for_board()
#   4. Validation: _validate_linked_profile()
#   5. Migration: old role modes → linked profiles
#   6. End-to-end: deal generation with linked profiles

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
    LinkedProfile,
    ProfileError,
    SeatProfile,
    SubProfile,
    migrate_profile_to_linked,
)
from bridge_engine.hand_profile_validate import validate_profile
from bridge_engine.deal_generator import (
    _apply_linked_profile,
    _select_subprofiles_for_board,
    _build_single_constrained_deal_v2,
    Seat,
)


# ===========================================================================
# 1. LinkedProfile dataclass tests
# ===========================================================================


class TestLinkedProfileDataclass:
    """Tests for LinkedProfile construction and methods."""

    def test_basic_construction(self) -> None:
        """LinkedProfile can be constructed with valid primary_seat and map."""
        lp = LinkedProfile(primary_seat="N", subprofile_map={0: [0], 1: [1]})
        assert lp.primary_seat == "N"
        assert lp.subprofile_map == {0: [0], 1: [1]}

    def test_secondary_seat_ns(self) -> None:
        """secondary_seat() returns the other seat in the pair."""
        assert LinkedProfile(primary_seat="N", subprofile_map={}).secondary_seat() == "S"
        assert LinkedProfile(primary_seat="S", subprofile_map={}).secondary_seat() == "N"

    def test_secondary_seat_ew(self) -> None:
        assert LinkedProfile(primary_seat="E", subprofile_map={}).secondary_seat() == "W"
        assert LinkedProfile(primary_seat="W", subprofile_map={}).secondary_seat() == "E"

    def test_pair_label(self) -> None:
        assert LinkedProfile(primary_seat="N", subprofile_map={}).pair_label() == "NS"
        assert LinkedProfile(primary_seat="S", subprofile_map={}).pair_label() == "NS"
        assert LinkedProfile(primary_seat="E", subprofile_map={}).pair_label() == "EW"
        assert LinkedProfile(primary_seat="W", subprofile_map={}).pair_label() == "EW"

    def test_invalid_primary_seat_raises(self) -> None:
        with pytest.raises(ProfileError, match="Invalid primary_seat"):
            LinkedProfile(primary_seat="X", subprofile_map={})

    def test_to_dict(self) -> None:
        lp = LinkedProfile(primary_seat="N", subprofile_map={0: [1, 2], 1: [0]})
        d = lp.to_dict()
        assert d["primary_seat"] == "N"
        # Keys should be strings for JSON compatibility.
        assert d["subprofile_map"] == {"0": [1, 2], "1": [0]}

    def test_from_dict(self) -> None:
        data = {"primary_seat": "S", "subprofile_map": {"0": [0], "1": [1, 2]}}
        lp = LinkedProfile.from_dict(data)
        assert lp.primary_seat == "S"
        assert lp.subprofile_map == {0: [0], 1: [1, 2]}

    def test_roundtrip(self) -> None:
        original = LinkedProfile(primary_seat="E", subprofile_map={0: [0, 1], 1: [1]})
        restored = LinkedProfile.from_dict(original.to_dict())
        assert restored.primary_seat == original.primary_seat
        assert restored.subprofile_map == original.subprofile_map

    def test_frozen(self) -> None:
        """LinkedProfile is frozen (immutable)."""
        lp = LinkedProfile(primary_seat="N", subprofile_map={0: [0]})
        with pytest.raises(AttributeError):
            lp.primary_seat = "S"  # type: ignore[misc]


# ===========================================================================
# 2. HandProfile integration tests
# ===========================================================================


class TestHandProfileLinkedFields:
    """Tests for ns/ew_linked_profile fields on HandProfile."""

    def _make_profile(
        self,
        ns_linked: Optional[LinkedProfile] = None,
        ew_linked: Optional[LinkedProfile] = None,
    ) -> HandProfile:
        std = _standard_all_open()
        return HandProfile(
            profile_name="TEST_LINKED",
            description="Linked profile test",
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
                "E": SeatProfile(
                    seat="E",
                    subprofiles=[
                        SubProfile(standard=std, weight_percent=50.0),
                        SubProfile(standard=std, weight_percent=50.0),
                    ],
                ),
                "W": SeatProfile(
                    seat="W",
                    subprofiles=[
                        SubProfile(standard=std, weight_percent=50.0),
                        SubProfile(standard=std, weight_percent=50.0),
                    ],
                ),
            },
            ns_linked_profile=ns_linked,
            ew_linked_profile=ew_linked,
        )

    def test_default_none(self) -> None:
        profile = self._make_profile()
        assert profile.ns_linked_profile is None
        assert profile.ew_linked_profile is None

    def test_ns_linked_profile_set(self) -> None:
        lp = LinkedProfile(primary_seat="N", subprofile_map={0: [0, 1], 1: [0, 1]})
        profile = self._make_profile(ns_linked=lp)
        assert profile.ns_linked_profile is lp

    def test_to_dict_without_linked(self) -> None:
        profile = self._make_profile()
        d = profile.to_dict()
        assert "ns_linked_profile" not in d
        assert "ew_linked_profile" not in d

    def test_to_dict_with_linked(self) -> None:
        lp = LinkedProfile(primary_seat="N", subprofile_map={0: [0], 1: [1]})
        profile = self._make_profile(ns_linked=lp)
        d = profile.to_dict()
        assert "ns_linked_profile" in d
        assert d["ns_linked_profile"]["primary_seat"] == "N"

    def test_from_dict_roundtrip_ns(self) -> None:
        lp = LinkedProfile(primary_seat="N", subprofile_map={0: [0, 1], 1: [1]})
        profile = self._make_profile(ns_linked=lp)
        d = profile.to_dict()
        restored = HandProfile.from_dict(d)
        assert restored.ns_linked_profile is not None
        assert restored.ns_linked_profile.primary_seat == "N"
        assert restored.ns_linked_profile.subprofile_map == {0: [0, 1], 1: [1]}

    def test_from_dict_roundtrip_ew(self) -> None:
        lp = LinkedProfile(primary_seat="E", subprofile_map={0: [0], 1: [0, 1]})
        profile = self._make_profile(ew_linked=lp)
        d = profile.to_dict()
        restored = HandProfile.from_dict(d)
        assert restored.ew_linked_profile is not None
        assert restored.ew_linked_profile.primary_seat == "E"
        assert restored.ew_linked_profile.subprofile_map == {0: [0], 1: [0, 1]}

    def test_from_dict_without_linked_defaults_none(self) -> None:
        """Legacy profile JSON without linked profile fields → None."""
        profile = self._make_profile()
        d = profile.to_dict()
        d.pop("ns_linked_profile", None)
        d.pop("ew_linked_profile", None)
        restored = HandProfile.from_dict(d)
        assert restored.ns_linked_profile is None
        assert restored.ew_linked_profile is None

    def test_json_file_roundtrip(self) -> None:
        """Full JSON file write → read roundtrip."""
        ns_lp = LinkedProfile(primary_seat="N", subprofile_map={0: [0, 1], 1: [0]})
        ew_lp = LinkedProfile(primary_seat="W", subprofile_map={0: [0], 1: [1]})
        profile = self._make_profile(ns_linked=ns_lp, ew_linked=ew_lp)
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            json.dump(profile.to_dict(), f)
            path = Path(f.name)
        try:
            with open(path) as f:
                raw = json.load(f)
            restored = HandProfile.from_dict(raw)
            assert restored.ns_linked_profile is not None
            assert restored.ns_linked_profile.subprofile_map == {0: [0, 1], 1: [0]}
            assert restored.ew_linked_profile is not None
            assert restored.ew_linked_profile.primary_seat == "W"
        finally:
            path.unlink()


# ===========================================================================
# 3. Stage 2 logic: _apply_linked_profile() tests
# ===========================================================================


class TestApplyLinkedProfile:
    """Tests for _apply_linked_profile() — the new coupling function."""

    def test_primary_picks_first_secondary_follows_map(self) -> None:
        """Primary picks by weight; secondary is constrained to mapped indices."""
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
        # N picks 0 (100% weight) → S must be 1 or 2.
        linked = LinkedProfile(primary_seat="N", subprofile_map={0: [1, 2], 1: [0]})
        rng = random.Random(42)

        for _ in range(100):
            chosen_subs: Dict[str, SubProfile] = {}
            chosen_idx: Dict[str, int] = {}
            _apply_linked_profile(rng, seat_profiles, linked, chosen_subs, chosen_idx)
            assert chosen_idx["N"] == 0
            assert chosen_idx["S"] in (1, 2), f"S should be 1 or 2, got {chosen_idx['S']}"

    def test_secondary_weights_respected(self) -> None:
        """Within mapped subset, secondary's own weights determine pick frequency."""
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
                    SubProfile(standard=std, weight_percent=90.0),  # Heavy
                    SubProfile(standard=std, weight_percent=5.0),  # Light
                    SubProfile(standard=std, weight_percent=5.0),  # Light
                ],
            ),
        }
        linked = LinkedProfile(primary_seat="N", subprofile_map={0: [0, 1], 1: [2]})
        rng = random.Random(42)

        counter: Counter[int] = Counter()
        for _ in range(2000):
            chosen_subs: Dict[str, SubProfile] = {}
            chosen_idx: Dict[str, int] = {}
            _apply_linked_profile(rng, seat_profiles, linked, chosen_subs, chosen_idx)
            counter[chosen_idx["S"]] += 1

        # N always picks 0 → S candidates are [0, 1]. S sub 0 weight 90, sub 1 weight 5.
        assert 2 not in counter, "S sub 2 should never be chosen"
        assert counter[0] > counter[1] * 5, f"Expected sub 0 >> sub 1, got {counter}"

    def test_single_mapped_secondary_always_chosen(self) -> None:
        """When map gives single secondary candidate, it's always chosen."""
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
        linked = LinkedProfile(primary_seat="N", subprofile_map={0: [1], 1: [0]})
        rng = random.Random(42)

        for _ in range(50):
            chosen_subs: Dict[str, SubProfile] = {}
            chosen_idx: Dict[str, int] = {}
            _apply_linked_profile(rng, seat_profiles, linked, chosen_subs, chosen_idx)
            assert chosen_idx["S"] == 1

    def test_ew_linked_profile(self) -> None:
        """Linked profile works for EW pair."""
        std = _standard_all_open()
        seat_profiles = {
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
                    SubProfile(standard=std, weight_percent=50.0),
                    SubProfile(standard=std, weight_percent=50.0),
                ],
            ),
        }
        linked = LinkedProfile(primary_seat="E", subprofile_map={0: [0, 1], 1: [1]})
        rng = random.Random(42)

        for _ in range(100):
            chosen_subs: Dict[str, SubProfile] = {}
            chosen_idx: Dict[str, int] = {}
            _apply_linked_profile(rng, seat_profiles, linked, chosen_subs, chosen_idx)
            assert chosen_idx["E"] == 0
            assert chosen_idx["W"] in (0, 1)

    def test_skips_when_single_subprofile(self) -> None:
        """Does nothing when primary or secondary has only 1 subprofile."""
        std = _standard_all_open()
        seat_profiles = {
            "N": SeatProfile(
                seat="N",
                subprofiles=[
                    SubProfile(standard=std, weight_percent=100.0),
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
        linked = LinkedProfile(primary_seat="N", subprofile_map={0: [0]})
        rng = random.Random(42)
        chosen_subs: Dict[str, SubProfile] = {}
        chosen_idx: Dict[str, int] = {}
        _apply_linked_profile(rng, seat_profiles, linked, chosen_subs, chosen_idx)
        # Should do nothing since N has only 1 subprofile.
        assert "N" not in chosen_idx
        assert "S" not in chosen_idx

    def test_unequal_subprofile_counts(self) -> None:
        """Linked profiles work with unequal subprofile counts."""
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
        linked = LinkedProfile(primary_seat="N", subprofile_map={0: [0], 1: [0, 1], 2: [1]})
        rng = random.Random(42)

        n_counter: Counter[int] = Counter()
        s_counter: Counter[int] = Counter()
        for _ in range(300):
            chosen_subs: Dict[str, SubProfile] = {}
            chosen_idx: Dict[str, int] = {}
            _apply_linked_profile(rng, seat_profiles, linked, chosen_subs, chosen_idx)
            n_counter[chosen_idx["N"]] += 1
            s_counter[chosen_idx["S"]] += 1

        assert set(n_counter.keys()) == {0, 1, 2}
        assert set(s_counter.keys()) == {0, 1}


# ===========================================================================
# 4. Integration: _select_subprofiles_for_board() with linked profiles
# ===========================================================================


class TestSelectSubprofilesWithLinked:
    """Tests for _select_subprofiles_for_board() using linked profiles."""

    def test_ns_linked_constrains_selection(self) -> None:
        """NS linked profile constrains S to mapped indices."""
        std = _standard_all_open()
        profile = HandProfile(
            profile_name="TEST_NS_LINKED",
            description="NS linked test",
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
            ns_linked_profile=LinkedProfile(
                primary_seat="N",
                subprofile_map={0: [0, 1], 1: [2]},
            ),
        )
        rng = random.Random(42)
        for _ in range(200):
            _subs, idxs = _select_subprofiles_for_board(rng, profile, ["N", "S", "E", "W"])
            n_idx = idxs["N"]
            s_idx = idxs["S"]
            if n_idx == 0:
                assert s_idx in (0, 1), f"N=0, S should be 0 or 1, got {s_idx}"
            elif n_idx == 1:
                assert s_idx == 2, f"N=1, S should be 2, got {s_idx}"

    def test_ew_linked_constrains_selection(self) -> None:
        """EW linked profile constrains W to mapped indices."""
        std = _standard_all_open()
        profile = HandProfile(
            profile_name="TEST_EW_LINKED",
            description="EW linked test",
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
                        SubProfile(standard=std, weight_percent=50.0),
                        SubProfile(standard=std, weight_percent=50.0),
                    ],
                ),
            },
            ew_linked_profile=LinkedProfile(
                primary_seat="E",
                subprofile_map={0: [0, 1], 1: [1]},
            ),
        )
        rng = random.Random(42)
        for _ in range(100):
            _subs, idxs = _select_subprofiles_for_board(rng, profile, ["N", "E", "S", "W"])
            assert idxs["E"] == 0
            assert idxs["W"] in (0, 1)

    def test_linked_profile_opposite_mapping(self) -> None:
        """Linked profile with opposite mapping: N=0 → S=1, N=1 → S=0."""
        std = _standard_all_open()
        profile = HandProfile(
            profile_name="TEST_LINKED_OPPOSITE",
            description="Linked with opposite mapping",
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
            # Linked profile maps 0→[1], 1→[0] (opposite).
            ns_linked_profile=LinkedProfile(
                primary_seat="N",
                subprofile_map={0: [1], 1: [0]},
            ),
        )
        rng = random.Random(42)
        for _ in range(50):
            _subs, idxs = _select_subprofiles_for_board(rng, profile, ["N", "S", "E", "W"])
            # Linked profile should win: N=0 → S=1 (not S=0 as role mode would do).
            assert idxs["N"] == 0
            assert idxs["S"] == 1

    def test_both_ns_and_ew_linked(self) -> None:
        """Both NS and EW linked profiles active simultaneously."""
        std = _standard_all_open()
        profile = HandProfile(
            profile_name="TEST_BOTH_LINKED",
            description="Both pairs linked",
            dealer="N",
            tag="Opener",
            hand_dealing_order=["N", "E", "S", "W"],
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
                        SubProfile(standard=std, weight_percent=50.0),
                        SubProfile(standard=std, weight_percent=50.0),
                    ],
                ),
            },
            ns_linked_profile=LinkedProfile(
                primary_seat="N",
                subprofile_map={0: [1], 1: [0]},
            ),
            ew_linked_profile=LinkedProfile(
                primary_seat="E",
                subprofile_map={0: [0], 1: [1]},
            ),
        )
        rng = random.Random(42)
        for _ in range(50):
            _subs, idxs = _select_subprofiles_for_board(rng, profile, ["N", "E", "S", "W"])
            assert idxs["N"] == 0
            assert idxs["S"] == 1  # Linked: N=0 → S=[1]
            assert idxs["E"] == 0
            assert idxs["W"] == 0  # Linked: E=0 → W=[0]


# ===========================================================================
# 5. End-to-end: deal generation with linked profiles
# ===========================================================================


class TestLinkedProfileE2E:
    """End-to-end tests through _build_single_constrained_deal_v2()."""

    def test_e2e_linked_produces_valid_deals(self) -> None:
        """Linked profile should produce valid deals through the full pipeline."""
        std = _standard_all_open()
        profile = HandProfile(
            profile_name="TEST_E2E_LINKED",
            description="E2E linked test",
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
            ns_linked_profile=LinkedProfile(
                primary_seat="N",
                subprofile_map={0: [0, 1], 1: [0, 1]},
            ),
        )
        rng = random.Random(42)
        for board in range(1, 6):
            deal = _build_single_constrained_deal_v2(rng, profile, board_number=board)
            assert deal is not None
            for seat in ("N", "E", "S", "W"):
                assert len(deal.hands[seat]) == 13


# ===========================================================================
# 6. Migration: old role modes → linked profiles
# ===========================================================================


class TestMigrateProfileToLinked:
    """Tests for migrate_profile_to_linked() — explicit migration on raw dicts."""

    def _make_raw(
        self,
        name: str = "TEST_MIGRATE",
        ns_role_mode: str = "no_driver_no_index",
        ew_role_mode: str = "no_driver_no_index",
        ns_bespoke_map: Optional[Dict[int, List[int]]] = None,
        ew_bespoke_map: Optional[Dict[int, List[int]]] = None,
        ns_linked_profile: Optional[Dict] = None,
        n_subs: int = 2,
        s_subs: int = 2,
        e_subs: int = 0,
        w_subs: int = 0,
        n_weights: Optional[List[float]] = None,
        s_weights: Optional[List[float]] = None,
    ) -> Dict:
        """Build a raw dict suitable for migrate_profile_to_linked()."""
        std = _standard_all_open()

        def _make_sp(seat: str, count: int, weights: Optional[List[float]] = None) -> Dict:
            if count == 0:
                return {"seat": seat, "subprofiles": []}
            w = weights or [round(100.0 / count, 1)] * count
            subs = [SubProfile(standard=std, weight_percent=w[i]).to_dict() for i in range(count)]
            return {"seat": seat, "subprofiles": subs}

        raw: Dict = {
            "profile_name": name,
            "description": "test",
            "dealer": "N",
            "tag": "Opener",
            "hand_dealing_order": ["N", "S", "E", "W"],
            "ns_role_mode": ns_role_mode,
            "ew_role_mode": ew_role_mode,
            "seat_profiles": {},
        }
        if n_subs > 0:
            raw["seat_profiles"]["N"] = _make_sp("N", n_subs, n_weights)
        if s_subs > 0:
            raw["seat_profiles"]["S"] = _make_sp("S", s_subs, s_weights)
        if e_subs > 0:
            raw["seat_profiles"]["E"] = _make_sp("E", e_subs)
        if w_subs > 0:
            raw["seat_profiles"]["W"] = _make_sp("W", w_subs)
        if ns_bespoke_map is not None:
            raw["ns_bespoke_map"] = {str(k): v for k, v in ns_bespoke_map.items()}
        if ew_bespoke_map is not None:
            raw["ew_bespoke_map"] = {str(k): v for k, v in ew_bespoke_map.items()}
        if ns_linked_profile is not None:
            raw["ns_linked_profile"] = ns_linked_profile
        return raw

    def test_no_driver_no_index_unchanged(self) -> None:
        """no_driver_no_index → no linked profile (no change)."""
        raw = self._make_raw(ns_role_mode="no_driver_no_index")
        result = migrate_profile_to_linked(raw)
        assert result.get("ns_linked_profile") is None
        assert result is raw  # Same dict (no change)

    def test_random_driver_unchanged(self) -> None:
        """random_driver → no linked profile (no change)."""
        raw = self._make_raw(ns_role_mode="random_driver")
        result = migrate_profile_to_linked(raw)
        assert result.get("ns_linked_profile") is None
        assert result is raw

    def test_north_drives_without_bespoke_unchanged(self) -> None:
        """north_drives without bespoke map → no linked profile."""
        raw = self._make_raw(ns_role_mode="north_drives")
        result = migrate_profile_to_linked(raw)
        assert result.get("ns_linked_profile") is None
        assert result is raw

    def test_north_drives_with_bespoke_migrates(self) -> None:
        """north_drives + bespoke map → LinkedProfile with N as primary."""
        bmap = {0: [0, 1], 1: [1]}
        raw = self._make_raw(ns_role_mode="north_drives", ns_bespoke_map=bmap)
        result = migrate_profile_to_linked(raw)
        lp = result.get("ns_linked_profile")
        assert lp is not None
        assert lp["primary_seat"] == "N"
        assert lp["subprofile_map"] == {"0": [0, 1], "1": [1]}
        # Old fields should be cleaned up.
        assert "ns_role_mode" not in result
        assert "ns_bespoke_map" not in result

    def test_south_drives_with_bespoke_migrates(self) -> None:
        """south_drives + bespoke map → LinkedProfile with S as primary."""
        bmap = {0: [0], 1: [0, 1], 2: [1]}
        raw = self._make_raw(
            ns_role_mode="south_drives",
            ns_bespoke_map=bmap,
            s_subs=3,
            s_weights=[34.0, 33.0, 33.0],
        )
        result = migrate_profile_to_linked(raw)
        lp = result.get("ns_linked_profile")
        assert lp is not None
        assert lp["primary_seat"] == "S"

    def test_no_driver_index_matching_migrates(self) -> None:
        """no_driver (index matching) → LinkedProfile with identity map."""
        raw = self._make_raw(ns_role_mode="no_driver")
        result = migrate_profile_to_linked(raw)
        lp = result.get("ns_linked_profile")
        assert lp is not None
        assert lp["primary_seat"] == "N"
        assert lp["subprofile_map"] == {"0": [0], "1": [1]}
        assert "ns_role_mode" not in result

    def test_no_driver_single_sub_no_migration(self) -> None:
        """no_driver with single subprofile → no linked profile."""
        raw = self._make_raw(ns_role_mode="no_driver", n_subs=1, s_subs=1)
        result = migrate_profile_to_linked(raw)
        assert result.get("ns_linked_profile") is None

    def test_ew_east_drives_with_bespoke_migrates(self) -> None:
        """EW east_drives + bespoke → LinkedProfile with E as primary."""
        ew_map = {0: [0, 1], 1: [1]}
        raw = self._make_raw(ew_role_mode="east_drives", ew_bespoke_map=ew_map, e_subs=2, w_subs=2)
        result = migrate_profile_to_linked(raw)
        lp = result.get("ew_linked_profile")
        assert lp is not None
        assert lp["primary_seat"] == "E"
        assert "ew_role_mode" not in result
        assert "ew_bespoke_map" not in result

    def test_already_has_linked_profile_unchanged(self) -> None:
        """Raw dict with existing linked profile is returned unchanged."""
        raw = self._make_raw(
            ns_linked_profile={"primary_seat": "N", "subprofile_map": {"0": [0], "1": [1]}},
        )
        result = migrate_profile_to_linked(raw)
        assert result is raw  # No change needed

    def test_no_driver_3_subs_identity_map(self) -> None:
        """no_driver with 3 subprofiles → identity map {0:[0], 1:[1], 2:[2]}."""
        raw = self._make_raw(
            ns_role_mode="no_driver",
            n_subs=3,
            s_subs=3,
            n_weights=[34.0, 33.0, 33.0],
            s_weights=[34.0, 33.0, 33.0],
        )
        result = migrate_profile_to_linked(raw)
        lp = result.get("ns_linked_profile")
        assert lp is not None
        assert lp["subprofile_map"] == {"0": [0], "1": [1], "2": [2]}

    def test_migrated_profile_works_e2e(self) -> None:
        """A migrated raw dict produces valid deals after from_dict()."""
        bmap = {0: [0, 1], 1: [0, 1]}
        raw = self._make_raw(ns_role_mode="north_drives", ns_bespoke_map=bmap)
        migrated_raw = migrate_profile_to_linked(raw)
        assert migrated_raw.get("ns_linked_profile") is not None

        profile = HandProfile.from_dict(migrated_raw)
        rng = random.Random(42)
        for board in range(1, 6):
            deal = _build_single_constrained_deal_v2(rng, profile, board_number=board)
            assert deal is not None
            for seat in ("N", "E", "S", "W"):
                assert len(deal.hands[seat]) == 13


# ===========================================================================
# 7. Validation: _validate_linked_profile() error cases
# ===========================================================================


class TestValidateLinkedProfile:
    """Tests for _validate_linked_profile() via validate_profile()."""

    def _make_linked_profile(
        self,
        ns_linked: Optional[LinkedProfile] = None,
        ew_linked: Optional[LinkedProfile] = None,
        num_n: int = 2,
        num_s: int = 2,
        num_e: int = 1,
        num_w: int = 1,
    ) -> HandProfile:
        std = _standard_all_open()

        def _subs(n: int) -> List[SubProfile]:
            w = 100.0 / n
            return [SubProfile(standard=std, weight_percent=w) for _ in range(n)]

        sp: Dict[str, SeatProfile] = {}
        if num_n > 0:
            sp["N"] = SeatProfile(seat="N", subprofiles=_subs(num_n))
        if num_s > 0:
            sp["S"] = SeatProfile(seat="S", subprofiles=_subs(num_s))
        if num_e > 0:
            sp["E"] = SeatProfile(seat="E", subprofiles=_subs(num_e))
        if num_w > 0:
            sp["W"] = SeatProfile(seat="W", subprofiles=_subs(num_w))

        return HandProfile(
            profile_name="TEST_VALIDATE_LINKED",
            description="test",
            dealer="N",
            tag="Opener",
            hand_dealing_order=["N", "S", "E", "W"],
            seat_profiles=sp,
            ns_linked_profile=ns_linked,
            ew_linked_profile=ew_linked,
        )

    def test_valid_linked_profile_passes(self) -> None:
        """A valid linked profile passes validation."""
        lp = LinkedProfile(primary_seat="N", subprofile_map={0: [0, 1], 1: [0, 1]})
        profile = self._make_linked_profile(ns_linked=lp)
        validated = validate_profile(profile)
        assert validated.ns_linked_profile is not None

    def test_valid_surjective_map_passes(self) -> None:
        """A surjective map where every secondary sub appears passes."""
        lp = LinkedProfile(primary_seat="N", subprofile_map={0: [0], 1: [1], 2: [0, 1]})
        profile = self._make_linked_profile(ns_linked=lp, num_n=3)
        validated = validate_profile(profile)
        assert validated.ns_linked_profile is not None

    def test_wrong_primary_seat_for_pair(self) -> None:
        """NS linked profile with E as primary → error."""
        lp = LinkedProfile(primary_seat="E", subprofile_map={0: [0], 1: [1]})
        profile = self._make_linked_profile(ns_linked=lp)
        with pytest.raises(ProfileError, match="primary_seat must be one of"):
            validate_profile(profile)

    def test_primary_too_few_subs(self) -> None:
        """Primary seat with 1 subprofile → error."""
        lp = LinkedProfile(primary_seat="N", subprofile_map={0: [0]})
        profile = self._make_linked_profile(ns_linked=lp, num_n=1)
        with pytest.raises(ProfileError, match="at least 2 subprofiles"):
            validate_profile(profile)

    def test_secondary_too_few_subs(self) -> None:
        """Secondary seat with 1 subprofile → error."""
        lp = LinkedProfile(primary_seat="N", subprofile_map={0: [0], 1: [0]})
        profile = self._make_linked_profile(ns_linked=lp, num_s=1)
        with pytest.raises(ProfileError, match="at least 2 subprofiles"):
            validate_profile(profile)

    def test_primary_index_out_of_bounds(self) -> None:
        """Primary key exceeding subprofile count → error."""
        lp = LinkedProfile(primary_seat="N", subprofile_map={0: [0, 1], 1: [0], 5: [1]})
        profile = self._make_linked_profile(ns_linked=lp)
        with pytest.raises(ProfileError, match="primary index 5 out of bounds"):
            validate_profile(profile)

    def test_secondary_index_out_of_bounds(self) -> None:
        """Secondary index exceeding subprofile count → error."""
        lp = LinkedProfile(primary_seat="N", subprofile_map={0: [0, 5], 1: [0]})
        profile = self._make_linked_profile(ns_linked=lp)
        with pytest.raises(ProfileError, match="secondary index 5.*out of bounds"):
            validate_profile(profile)

    def test_missing_primary_key(self) -> None:
        """Not all primary indices present as keys → error."""
        lp = LinkedProfile(primary_seat="N", subprofile_map={0: [0, 1]})  # Missing key 1
        profile = self._make_linked_profile(ns_linked=lp)
        with pytest.raises(ProfileError, match="primary sub index 1 is missing"):
            validate_profile(profile)

    def test_secondary_not_surjective(self) -> None:
        """Secondary sub not in any mapping → error."""
        lp = LinkedProfile(primary_seat="N", subprofile_map={0: [0], 1: [0]})  # Sub 1 never used
        profile = self._make_linked_profile(ns_linked=lp)
        with pytest.raises(ProfileError, match="secondary sub index 1 does not appear"):
            validate_profile(profile)

    def test_empty_value_list(self) -> None:
        """Empty mapping list → error."""
        lp = LinkedProfile(primary_seat="N", subprofile_map={0: [], 1: [0, 1]})
        profile = self._make_linked_profile(ns_linked=lp)
        with pytest.raises(ProfileError, match="empty secondary mapping"):
            validate_profile(profile)

    def test_ew_linked_validation(self) -> None:
        """EW linked profile validation works correctly."""
        lp = LinkedProfile(primary_seat="E", subprofile_map={0: [0, 1], 1: [0, 1]})
        profile = self._make_linked_profile(ew_linked=lp, num_e=2, num_w=2)
        validated = validate_profile(profile)
        assert validated.ew_linked_profile is not None

    def test_no_linked_profile_passes(self) -> None:
        """Profile without linked profiles passes validation."""
        profile = self._make_linked_profile()
        validated = validate_profile(profile)
        assert validated.ns_linked_profile is None
        assert validated.ew_linked_profile is None
