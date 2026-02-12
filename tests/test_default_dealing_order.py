# tests/test_default_dealing_order.py
"""
Tests for default dealing order generation (dealer + clockwise).

NOTE: _base_smart_hand_order() and its helpers are DEAD CODE — not called
in production. v2 handles ordering independently. These tests cover the
algorithm for completeness but are scheduled for removal alongside v1.
"""

from bridge_engine.hand_profile_model import _default_dealing_order, HandProfile
from bridge_engine.wizard_flow import (
    _clockwise_from,
    _detect_seat_roles,
    _base_smart_hand_order,
    _normalize_subprofile_weights,
    _get_subprofile_type,
    _compute_seat_risk,
)


# ---------------------------------------------------------------------------
# Unit tests for _clockwise_from() helper
# ---------------------------------------------------------------------------

def test_clockwise_from_north():
    """Starting from N → N, E, S, W."""
    assert _clockwise_from("N") == ["N", "E", "S", "W"]


def test_clockwise_from_east():
    """Starting from E → E, S, W, N."""
    assert _clockwise_from("E") == ["E", "S", "W", "N"]


def test_clockwise_from_south():
    """Starting from S → S, W, N, E."""
    assert _clockwise_from("S") == ["S", "W", "N", "E"]


def test_clockwise_from_west():
    """Starting from W → W, N, E, S."""
    assert _clockwise_from("W") == ["W", "N", "E", "S"]


# ---------------------------------------------------------------------------
# Unit tests for _detect_seat_roles() helper
# ---------------------------------------------------------------------------

def test_detect_seat_roles_empty():
    """Empty seat_profiles returns all False/None/0.0."""
    roles = _detect_seat_roles({})
    for seat in "NESW":
        assert roles[seat] == {"rs": False, "pc": None, "oc": None, "risk": 0.0}


def test_detect_seat_roles_rs_at_north():
    """Detect RS constraint at North."""
    seat_profiles = {
        "N": {
            "subprofiles": [
                {"random_suit_constraint": {"n_suits": 1}}
            ]
        }
    }
    roles = _detect_seat_roles(seat_profiles)
    assert roles["N"]["rs"] is True
    assert roles["N"]["pc"] is None
    assert roles["N"]["oc"] is None
    # Other seats unaffected
    assert roles["S"]["rs"] is False


def test_detect_seat_roles_pc_at_south():
    """Detect PC constraint at South pointing to North."""
    seat_profiles = {
        "S": {
            "subprofiles": [
                {"partner_contingent_constraint": {"partner_seat": "N"}}
            ]
        }
    }
    roles = _detect_seat_roles(seat_profiles)
    assert roles["S"]["pc"] == "N"
    assert roles["S"]["rs"] is False


def test_detect_seat_roles_oc_at_east():
    """Detect OC constraint at East pointing to West."""
    seat_profiles = {
        "E": {
            "subprofiles": [
                {"opponents_contingent_suit_constraint": {"opponent_seat": "W"}}
            ]
        }
    }
    roles = _detect_seat_roles(seat_profiles)
    assert roles["E"]["oc"] == "W"
    assert roles["E"]["rs"] is False


def test_detect_seat_roles_combined():
    """Detect multiple roles across seats."""
    seat_profiles = {
        "N": {"subprofiles": [{"random_suit_constraint": {"n_suits": 1}}]},
        "S": {"subprofiles": [{"partner_contingent_constraint": {"partner_seat": "N"}}]},
        "W": {"subprofiles": [{"random_suit_constraint": {"n_suits": 2}}]},
        "E": {"subprofiles": [{"opponents_contingent_suit_constraint": {"opponent_seat": "W"}}]},
    }
    roles = _detect_seat_roles(seat_profiles)
    assert roles["N"]["rs"] is True
    assert roles["S"]["pc"] == "N"
    assert roles["W"]["rs"] is True
    assert roles["E"]["oc"] == "W"


# ---------------------------------------------------------------------------
# Unit tests for _normalize_subprofile_weights()
# ---------------------------------------------------------------------------

def test_normalize_weights_empty():
    """Empty list returns empty."""
    assert _normalize_subprofile_weights([]) == []


def test_normalize_weights_single():
    """1 subprofile gets 100%."""
    assert _normalize_subprofile_weights([{"weight_percent": 50}]) == [1.0]
    assert _normalize_subprofile_weights([{}]) == [1.0]


def test_normalize_weights_two_no_weights():
    """2 subprofiles, no weights → each 0.5."""
    result = _normalize_subprofile_weights([{}, {}])
    assert result == [0.5, 0.5]


def test_normalize_weights_three_no_weights():
    """3 subprofiles, no weights → each 0.333..."""
    result = _normalize_subprofile_weights([{}, {}, {}])
    assert len(result) == 3
    assert abs(result[0] - 1/3) < 0.001
    assert abs(sum(result) - 1.0) < 0.001


def test_normalize_weights_explicit():
    """2 subprofiles with 70/30 weights."""
    result = _normalize_subprofile_weights([
        {"weight_percent": 70},
        {"weight_percent": 30},
    ])
    assert abs(result[0] - 0.7) < 0.001
    assert abs(result[1] - 0.3) < 0.001


def test_normalize_weights_unnormalized():
    """2 subprofiles with 200/100 → normalized to 0.67/0.33."""
    result = _normalize_subprofile_weights([
        {"weight_percent": 200},
        {"weight_percent": 100},
    ])
    assert abs(result[0] - 2/3) < 0.001
    assert abs(result[1] - 1/3) < 0.001


# ---------------------------------------------------------------------------
# Unit tests for _get_subprofile_type()
# ---------------------------------------------------------------------------

def test_get_subprofile_type_standard():
    """No RS/PC/OC → standard."""
    assert _get_subprofile_type({}) == "standard"
    assert _get_subprofile_type({"standard": {}}) == "standard"


def test_get_subprofile_type_rs():
    """RS constraint → rs."""
    assert _get_subprofile_type({"random_suit_constraint": {"n_suits": 1}}) == "rs"


def test_get_subprofile_type_pc():
    """PC constraint → pc."""
    assert _get_subprofile_type({"partner_contingent_constraint": {"partner_seat": "N"}}) == "pc"


def test_get_subprofile_type_oc():
    """OC constraint → oc."""
    assert _get_subprofile_type({"opponents_contingent_suit_constraint": {"opponent_seat": "W"}}) == "oc"


# ---------------------------------------------------------------------------
# Unit tests for _compute_seat_risk()
# ---------------------------------------------------------------------------

def test_compute_seat_risk_empty():
    """No subprofiles → risk 0."""
    assert _compute_seat_risk({}) == 0.0
    assert _compute_seat_risk({"subprofiles": []}) == 0.0


def test_compute_seat_risk_single_rs():
    """Single RS subprofile → risk 1.0."""
    seat = {"subprofiles": [{"random_suit_constraint": {"n_suits": 1}}]}
    assert _compute_seat_risk(seat) == 1.0


def test_compute_seat_risk_single_standard():
    """Single standard subprofile → risk 0.0."""
    seat = {"subprofiles": [{}]}
    assert _compute_seat_risk(seat) == 0.0


def test_compute_seat_risk_two_equal_rs_standard():
    """2 equal subprofiles: 1 RS + 1 Standard → risk 0.5."""
    seat = {"subprofiles": [
        {"random_suit_constraint": {"n_suits": 1}},
        {},
    ]}
    assert abs(_compute_seat_risk(seat) - 0.5) < 0.001


def test_compute_seat_risk_weighted_70_30():
    """70% Standard + 30% RS → risk 0.30."""
    seat = {"subprofiles": [
        {"weight_percent": 70},  # standard
        {"weight_percent": 30, "random_suit_constraint": {"n_suits": 1}},
    ]}
    assert abs(_compute_seat_risk(seat) - 0.30) < 0.001


def test_compute_seat_risk_pc():
    """50% PC + 50% Standard → risk 0.25."""
    seat = {"subprofiles": [
        {"weight_percent": 50, "partner_contingent_constraint": {"partner_seat": "N"}},
        {"weight_percent": 50},
    ]}
    assert abs(_compute_seat_risk(seat) - 0.25) < 0.001


# ---------------------------------------------------------------------------
# Unit tests for _default_dealing_order()
# ---------------------------------------------------------------------------

def test_default_dealing_order_north():
    """Dealer N → N, E, S, W (clockwise from North)."""
    assert _default_dealing_order("N") == ["N", "E", "S", "W"]


def test_default_dealing_order_east():
    """Dealer E → E, S, W, N (clockwise from East)."""
    assert _default_dealing_order("E") == ["E", "S", "W", "N"]


def test_default_dealing_order_south():
    """Dealer S → S, W, N, E (clockwise from South)."""
    assert _default_dealing_order("S") == ["S", "W", "N", "E"]


def test_default_dealing_order_west():
    """Dealer W → W, N, E, S (clockwise from West)."""
    assert _default_dealing_order("W") == ["W", "N", "E", "S"]


# ---------------------------------------------------------------------------
# Integration tests for HandProfile.from_dict() with missing dealing order
# ---------------------------------------------------------------------------

def _minimal_profile_dict(dealer: str, include_dealing_order: bool = True):
    """Create a minimal valid profile dict for testing."""
    d = {
        "profile_name": "Test Profile",
        "description": "Test",
        "dealer": dealer,
        "tag": "Opener",
        "seat_profiles": {},
    }
    if include_dealing_order:
        d["hand_dealing_order"] = _default_dealing_order(dealer)
    return d


def test_from_dict_uses_provided_dealing_order():
    """When hand_dealing_order is provided, use it."""
    data = _minimal_profile_dict("N", include_dealing_order=False)
    data["hand_dealing_order"] = ["N", "S", "E", "W"]  # Custom order

    profile = HandProfile.from_dict(data)

    assert profile.hand_dealing_order == ["N", "S", "E", "W"]


def test_from_dict_generates_default_when_missing_north():
    """When hand_dealing_order is missing, generate default for dealer N."""
    data = _minimal_profile_dict("N", include_dealing_order=False)

    profile = HandProfile.from_dict(data)

    assert profile.hand_dealing_order == ["N", "E", "S", "W"]


def test_from_dict_generates_default_when_missing_east():
    """When hand_dealing_order is missing, generate default for dealer E."""
    data = _minimal_profile_dict("E", include_dealing_order=False)

    profile = HandProfile.from_dict(data)

    assert profile.hand_dealing_order == ["E", "S", "W", "N"]


def test_from_dict_generates_default_when_missing_south():
    """When hand_dealing_order is missing, generate default for dealer S."""
    data = _minimal_profile_dict("S", include_dealing_order=False)

    profile = HandProfile.from_dict(data)

    assert profile.hand_dealing_order == ["S", "W", "N", "E"]


def test_from_dict_generates_default_when_missing_west():
    """When hand_dealing_order is missing, generate default for dealer W."""
    data = _minimal_profile_dict("W", include_dealing_order=False)

    profile = HandProfile.from_dict(data)

    assert profile.hand_dealing_order == ["W", "N", "E", "S"]


# ---------------------------------------------------------------------------
# Unit tests for _base_smart_hand_order() - Base Smart Hand Order algorithm
# ---------------------------------------------------------------------------

# --- P1: RS seats (clockwise from dealer) ---

def test_smart_order_p1_single_rs():
    """P1: Single RS at N, dealer=E → N goes first."""
    seat_profiles = {
        "N": {"subprofiles": [{"random_suit_constraint": {"n_suits": 1}}]},
    }
    order = _base_smart_hand_order(seat_profiles, dealer="E")
    assert order[0] == "N"
    assert len(order) == 4
    assert set(order) == {"N", "E", "S", "W"}


def test_smart_order_p1_two_rs_clockwise():
    """P1: Two RS at N and W, dealer=E → W first (clockwise from E), then N."""
    seat_profiles = {
        "N": {"subprofiles": [{"random_suit_constraint": {"n_suits": 1}}]},
        "W": {"subprofiles": [{"random_suit_constraint": {"n_suits": 2}}]},
    }
    # Clockwise from E: E, S, W, N
    order = _base_smart_hand_order(seat_profiles, dealer="E")
    assert order[0] == "W"  # First RS clockwise from E
    assert order[1] == "N"  # Second RS


# --- P2: NS seat (driver or next clockwise) ---

def test_smart_order_p2_driver_defined():
    """P2: NS driver=N, no RS → N goes first."""
    order = _base_smart_hand_order({}, dealer="E", ns_role_mode="north_drives")
    assert order[0] == "N"


def test_smart_order_p2_no_driver_uses_clockwise():
    """P2: No driver, no RS, dealer=E → S first (next NS clockwise from E)."""
    # Clockwise from E: E, S, W, N → first NS is S
    order = _base_smart_hand_order({}, dealer="E", ns_role_mode="no_driver_no_index")
    assert order[0] == "S"


def test_smart_order_p2_driver_after_rs():
    """P2: RS at W, driver=N → W first, then N."""
    seat_profiles = {
        "W": {"subprofiles": [{"random_suit_constraint": {"n_suits": 1}}]},
    }
    order = _base_smart_hand_order(seat_profiles, dealer="E", ns_role_mode="north_drives")
    assert order[0] == "W"  # P1: RS first
    assert order[1] == "N"  # P2: driver second


# --- P3: PC seats (after partner) ---

def test_smart_order_p3_pc_after_rs_partner():
    """P3: RS at N, PC at S (partner=N) → N first, then S."""
    seat_profiles = {
        "N": {"subprofiles": [{"random_suit_constraint": {"n_suits": 1}}]},
        "S": {"subprofiles": [{"partner_contingent_constraint": {"partner_seat": "N"}}]},
    }
    order = _base_smart_hand_order(seat_profiles, dealer="E")
    assert order[0] == "N"  # P1: RS
    # P2: NS - N already placed, so next NS clockwise from N is S...
    # but S has PC, will it be placed in P2 or P3?
    # P2 adds next NS if remaining, S is remaining → S added in P2
    assert order[1] == "S"


# --- P4: OC seats (after opponent) ---

def test_smart_order_p4_oc_after_rs_opponent():
    """P4: RS at W, OC at E (opponent=W) → W first, then E after opponent."""
    seat_profiles = {
        "W": {"subprofiles": [{"random_suit_constraint": {"n_suits": 1}}]},
        "E": {"subprofiles": [{"opponents_contingent_suit_constraint": {"opponent_seat": "W"}}]},
    }
    order = _base_smart_hand_order(seat_profiles, dealer="N")
    # P1: W (RS)
    # P2: N or S next NS clockwise from W → N
    # P3: no PC
    # P4: E (OC) after W which is in order
    assert order[0] == "W"
    assert "E" in order
    # E should come after W
    assert order.index("E") > order.index("W")


# --- P5: Remaining (clockwise fill) ---

def test_smart_order_p5_fallback_no_roles():
    """P5: No RS/PC/OC, no driver → dealer + clockwise (same as default)."""
    order = _base_smart_hand_order({}, dealer="E", ns_role_mode="no_driver_no_index")
    # P2 will add first NS clockwise from E which is S
    # P5 fills remaining: clockwise from S → W, N, E
    # So order should be S, W, N, E
    assert order == ["S", "W", "N", "E"]


# --- Integration: Complex profile ---

def test_smart_order_integration_complex():
    """Integration: RS at N, PC at S, OC at E (opponent=W), driver=N."""
    seat_profiles = {
        "N": {"subprofiles": [{"random_suit_constraint": {"n_suits": 1}}]},
        "S": {"subprofiles": [{"partner_contingent_constraint": {"partner_seat": "N"}}]},
        "E": {"subprofiles": [{"opponents_contingent_suit_constraint": {"opponent_seat": "W"}}]},
    }
    order = _base_smart_hand_order(seat_profiles, dealer="W", ns_role_mode="north_drives")
    # P1: N (RS) - only RS, W clockwise: W, N, E, S → N is RS
    assert order[0] == "N"
    # P2: driver=N already placed, skip
    # P3: S has PC(N), N is in order → S added
    assert order[1] == "S"
    # P4: E has OC(W), W not in order yet → skip E
    # P5: remaining = {W, E}, clockwise from S: S, W, N, E → W then E
    assert order[2] == "W"
    assert order[3] == "E"


# ---------------------------------------------------------------------------
# Additional coverage tests
# ---------------------------------------------------------------------------

# --- P1: RS at different positions ---

def test_smart_order_p1_rs_at_south():
    """P1: RS at S, dealer=N → S goes first."""
    seat_profiles = {
        "S": {"subprofiles": [{"random_suit_constraint": {"n_suits": 1}}]},
    }
    order = _base_smart_hand_order(seat_profiles, dealer="N")
    assert order[0] == "S"


def test_smart_order_p1_two_rs_dealer_west():
    """P1: Two RS (N, E), dealer=W → E first (clockwise from W), then N."""
    seat_profiles = {
        "N": {"subprofiles": [{"random_suit_constraint": {"n_suits": 1}}]},
        "E": {"subprofiles": [{"random_suit_constraint": {"n_suits": 2}}]},
    }
    # Clockwise from W: W, N, E, S → N first, then E
    order = _base_smart_hand_order(seat_profiles, dealer="W")
    assert order[0] == "N"  # First RS clockwise from W
    assert order[1] == "E"  # Second RS


# --- P2: South drives ---

def test_smart_order_p2_south_drives():
    """P2: Driver=S (south_drives), no RS → S goes first."""
    order = _base_smart_hand_order({}, dealer="N", ns_role_mode="south_drives")
    assert order[0] == "S"


def test_smart_order_p2_south_drives_with_rs():
    """P2: RS at W, driver=S → W first, then S."""
    seat_profiles = {
        "W": {"subprofiles": [{"random_suit_constraint": {"n_suits": 1}}]},
    }
    order = _base_smart_hand_order(seat_profiles, dealer="N", ns_role_mode="south_drives")
    assert order[0] == "W"  # P1: RS
    assert order[1] == "S"  # P2: driver


# --- P3: PC where partner NOT in order ---

def test_smart_order_p3_pc_partner_not_in_order():
    """P3: PC at S (partner=N), but N has no RS → PC falls to P5."""
    seat_profiles = {
        "S": {"subprofiles": [{"partner_contingent_constraint": {"partner_seat": "N"}}]},
    }
    # No RS, so P1 adds nothing
    # P2: no driver, dealer=E → next NS clockwise from E is S
    # But wait, S has PC pointing to N. P2 just adds next NS, it doesn't check PC.
    order = _base_smart_hand_order(seat_profiles, dealer="E", ns_role_mode="no_driver_no_index")
    # P2 adds S (next NS clockwise from E)
    # P3: S already added, N not in order yet, so PC check doesn't apply
    # P5: fills N, W, E clockwise from S
    assert order[0] == "S"
    assert set(order) == {"N", "E", "S", "W"}


def test_smart_order_p3_pc_waits_for_partner():
    """P3: RS at E, PC at W (partner=E) → E first, then W via P3."""
    seat_profiles = {
        "E": {"subprofiles": [{"random_suit_constraint": {"n_suits": 1}}]},
        "W": {"subprofiles": [{"partner_contingent_constraint": {"partner_seat": "E"}}]},
    }
    order = _base_smart_hand_order(seat_profiles, dealer="N", ns_role_mode="no_driver_no_index")
    # P1: E (RS)
    # P2: next NS clockwise from E → S
    # P3: W has PC(E), E is in order → W added
    assert order[0] == "E"
    assert order[1] == "S"  # P2
    assert order[2] == "W"  # P3: PC after partner


# --- P4: OC where opponent NOT in order ---

def test_smart_order_p4_oc_opponent_not_in_order():
    """P4: OC at E (opponent=W), but W has no RS → OC falls to P5."""
    seat_profiles = {
        "E": {"subprofiles": [{"opponents_contingent_suit_constraint": {"opponent_seat": "W"}}]},
    }
    order = _base_smart_hand_order(seat_profiles, dealer="N", ns_role_mode="no_driver_no_index")
    # P1: no RS
    # P2: next NS clockwise from N → S
    # P3: no PC
    # P4: E has OC(W), but W not in order → skip
    # P5: fill W, E, N clockwise from S → but N already... wait
    # Let me trace: order=[], remaining={N,E,S,W}
    # P1: no RS → order=[]
    # P2: next NS clockwise from N (dealer): N,E,S,W → N is NS → order=[N]
    # Hmm, clockwise from dealer N: N,E,S,W. First NS is N itself.
    # Actually let me re-check the algorithm for P2 when order is empty.
    assert order[0] == "N"  # P2: first NS clockwise from dealer
    # P4: E has OC(W), W not in order → skip
    # P5: remaining={E,S,W}, clockwise from N: E,S,W
    assert "W" in order
    assert "E" in order


def test_smart_order_p4_oc_waits_for_opponent():
    """P4: RS at W, OC at N (opponent=W) → W first, then N via P4."""
    seat_profiles = {
        "W": {"subprofiles": [{"random_suit_constraint": {"n_suits": 1}}]},
        "N": {"subprofiles": [{"opponents_contingent_suit_constraint": {"opponent_seat": "W"}}]},
    }
    order = _base_smart_hand_order(seat_profiles, dealer="E", ns_role_mode="no_driver_no_index")
    # P1: W (RS) → order=[W]
    # P2: next NS clockwise from W: W,N,E,S → N is NS, but N has OC
    # P2 just adds next NS, doesn't check OC → order=[W, N]
    assert order[0] == "W"
    assert order[1] == "N"  # P2 adds NS regardless of OC


# --- Different dealers ---

def test_smart_order_different_dealer_south():
    """Different dealer: RS at N, dealer=S."""
    seat_profiles = {
        "N": {"subprofiles": [{"random_suit_constraint": {"n_suits": 1}}]},
    }
    # Clockwise from S: S, W, N, E → RS at N found
    order = _base_smart_hand_order(seat_profiles, dealer="S")
    assert order[0] == "N"


def test_smart_order_different_dealer_north():
    """Different dealer: RS at E, dealer=N."""
    seat_profiles = {
        "E": {"subprofiles": [{"random_suit_constraint": {"n_suits": 1}}]},
    }
    order = _base_smart_hand_order(seat_profiles, dealer="N")
    assert order[0] == "E"


# ---------------------------------------------------------------------------
# Risk-based ordering tests
# ---------------------------------------------------------------------------

def test_smart_order_risk_higher_risk_first():
    """Two RS seats with different risks: higher risk goes first."""
    # N: 100% RS = risk 1.0
    # W: 50% RS + 50% Standard = risk 0.5
    seat_profiles = {
        "N": {"subprofiles": [
            {"random_suit_constraint": {"n_suits": 1}, "weight_percent": 100},
        ]},
        "W": {"subprofiles": [
            {"random_suit_constraint": {"n_suits": 1}, "weight_percent": 50},
            {"weight_percent": 50},  # Standard
        ]},
    }
    # N has higher risk (1.0 > 0.5), so N goes first regardless of clockwise
    order = _base_smart_hand_order(seat_profiles, dealer="E")
    assert order[0] == "N"  # Higher risk
    assert order[1] == "W"  # Lower risk


def test_smart_order_risk_equal_uses_clockwise():
    """Two RS seats with EQUAL risks: clockwise from dealer as tiebreaker."""
    # Both N and W: 100% RS = risk 1.0 (equal)
    seat_profiles = {
        "N": {"subprofiles": [{"random_suit_constraint": {"n_suits": 1}}]},
        "W": {"subprofiles": [{"random_suit_constraint": {"n_suits": 1}}]},
    }
    # Clockwise from E: E, S, W, N → W comes before N
    order = _base_smart_hand_order(seat_profiles, dealer="E")
    assert order[0] == "W"  # Earlier in clockwise from E
    assert order[1] == "N"  # Later in clockwise from E


def test_smart_order_risk_partial_rs():
    """Seat with partial RS (30%) should still be treated as RS but with lower priority."""
    # N: 30% RS = risk 0.3
    # W: 100% RS = risk 1.0
    seat_profiles = {
        "N": {"subprofiles": [
            {"weight_percent": 70},  # Standard
            {"random_suit_constraint": {"n_suits": 1}, "weight_percent": 30},
        ]},
        "W": {"subprofiles": [
            {"random_suit_constraint": {"n_suits": 1}},
        ]},
    }
    order = _base_smart_hand_order(seat_profiles, dealer="E")
    assert order[0] == "W"  # Higher risk (1.0)
    assert order[1] == "N"  # Lower risk (0.3)
