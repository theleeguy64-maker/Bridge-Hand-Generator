# tests/test_rs_pc_sandbox_profile.py

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from bridge_engine import deal_generator


@dataclass
class _SandboxSubprofile:
    """
    Minimal stub representing one subprofile.

    We only care about:
      - random_suit_constraint presence to mark RS seats.
      - partner_contingent_constraint presence to mark PC seats.

    All other real constraint fields are intentionally omitted.
    """

    random_suit_constraint: Optional[object] = None
    partner_contingent_constraint: Optional[object] = None
    opponents_contingent_suit_constraint: Optional[object] = None


@dataclass
class _SandboxSeatProfile:
    """
    Minimal SeatProfile-like stub.

    deal_generator only requires that:
      - the object is an instance of whatever it thinks SeatProfile is, and
      - it has a .subprofiles list.
    """

    subprofiles: List[_SandboxSubprofile]


@dataclass
class _SandboxProfile:
    """
    Duck-typed profile for RS/PC sandbox experiments.

    We provide just enough structure for _build_single_constrained_deal
    to interact with it, but this profile is used ONLY in tests.
    """

    dealer: str
    hand_dealing_order: List[str]
    seat_profiles: Dict[str, _SandboxSeatProfile]
    profile_name: str = "RS_PC_sandbox_v2"
    ns_index_coupling_enabled: bool = False
    is_invariants_safety_profile: bool = False


def make_rs_pc_sandbox_profile() -> _SandboxProfile:
    """
    Build a minimal RS+PC sandbox profile for future constructive-help v2 tests.

    Shape:
      - West ("W"): Random Suit seat        -> random_suit_constraint present.
      - East ("E"): Random Suit seat        -> random_suit_constraint present.
      - North ("N"): Partner-Contingent seat -> partner_contingent_constraint present.
      - South ("S"): Standard-only / unconstrained for this sandbox.

    This is intentionally *not* wired into generate_deals or any CLI path;
    it exists purely as a test-only lab profile for RS/PC experiments.
    """
    # RS seats: W and E
    rs_sub = _SandboxSubprofile(random_suit_constraint=object())

    # PC seat: N
    pc_sub = _SandboxSubprofile(partner_contingent_constraint=object())

    # Plain standard-only seat for S (no non-standard constraints).
    std_sub = _SandboxSubprofile()

    seat_profiles: Dict[str, _SandboxSeatProfile] = {
        "N": _SandboxSeatProfile(subprofiles=[pc_sub]),
        "E": _SandboxSeatProfile(subprofiles=[rs_sub]),
        "S": _SandboxSeatProfile(subprofiles=[std_sub]),
        "W": _SandboxSeatProfile(subprofiles=[rs_sub]),
    }

    return _SandboxProfile(
        dealer="N",
        hand_dealing_order=["N", "E", "S", "W"],
        seat_profiles=seat_profiles,
    )


# ---------------------------------------------------------------------------
# Skeleton tests: shape only, no behavioural changes yet.
# ---------------------------------------------------------------------------


def test_rs_pc_sandbox_profile_shape() -> None:
    """
    Basic sanity on the RS/PC sandbox profile:

      - It has all four seats.
      - W and E are marked as Random Suit seats.
      - N is marked as Partner-Contingent.
      - S has no non-standard constraints.
    """
    profile = make_rs_pc_sandbox_profile()

    assert profile.profile_name == "RS_PC_sandbox_v2"
    assert profile.dealer == "N"
    assert profile.hand_dealing_order == ["N", "E", "S", "W"]

    # Make the deal generator treat our stub as its SeatProfile type.
    # We don't call into the generator yet; this is just to sanity-check
    # that the structure is compatible with its expectations.
    SeatProfile = getattr(deal_generator, "SeatProfile", None)
    assert SeatProfile is not None

    # Shape: four seats.
    assert set(profile.seat_profiles.keys()) == {"N", "E", "S", "W"}

    n_profile = profile.seat_profiles["N"]
    e_profile = profile.seat_profiles["E"]
    s_profile = profile.seat_profiles["S"]
    w_profile = profile.seat_profiles["W"]

    # Each seat should have exactly one subprofile in this sandbox.
    assert len(n_profile.subprofiles) == 1
    assert len(e_profile.subprofiles) == 1
    assert len(s_profile.subprofiles) == 1
    assert len(w_profile.subprofiles) == 1

    n_sub = n_profile.subprofiles[0]
    e_sub = e_profile.subprofiles[0]
    s_sub = s_profile.subprofiles[0]
    w_sub = w_profile.subprofiles[0]

    # W/E: Random Suit seats.
    assert n_sub.random_suit_constraint is None
    assert e_sub.random_suit_constraint is not None
    assert w_sub.random_suit_constraint is not None

    # N: Partner-Contingent.
    assert n_sub.partner_contingent_constraint is not None

    # S: standard-only (no non-standard constraints).
    assert s_sub.random_suit_constraint is None
    assert s_sub.partner_contingent_constraint is None
    assert s_sub.opponents_contingent_suit_constraint is None
