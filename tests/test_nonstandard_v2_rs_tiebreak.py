from bridge_engine import deal_generator as dg


def test_v2_weighted_order_prefers_higher_success_rate():
    candidate = ["S", "H", "D", "C"]
    rs_entry = {
        "buckets": {
            # success rates:
            # H: 8/10 = 0.8 (high)
            # S: 2/10 = 0.2 (low)
            "H": {"seen_attempts": 10, "matched_attempts": 8},
            "S": {"seen_attempts": 10, "matched_attempts": 2},
            # D/C absent => default 0/0 => treated as rate 0.0
        }
    }

    ordered = dg._v2_order_rs_suits_weighted(candidate, rs_entry)
    assert ordered.index("H") < ordered.index("S")


def test_v2_weighted_order_breaks_ties_by_seen_then_original():
    candidate = ["S", "H", "D", "C"]
    rs_entry = {
        "buckets": {
            # H and D have same rate (0.5), but D has fewer seen => should come first
            "H": {"seen_attempts": 10, "matched_attempts": 5},
            "D": {"seen_attempts": 2, "matched_attempts": 1},
        }
    }

    ordered = dg._v2_order_rs_suits_weighted(candidate, rs_entry)
    assert ordered.index("D") < ordered.index("H")


def test_v2_weighted_order_stable_with_no_stats():
    candidate = ["S", "H", "D", "C"]
    ordered = dg._v2_order_rs_suits_weighted(candidate, {"buckets": {}})
    assert ordered == candidate