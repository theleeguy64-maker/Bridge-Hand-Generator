from bridge_engine import deal_generator as dg


def test_v2_order_rs_suits_by_seen_attempts_stable():
    candidate = ["S", "H", "D", "C"]
    rs_entry = {
        "buckets": {
            "S": {"seen_attempts": 5, "matched_attempts": 5},
            "H": {"seen_attempts": 1, "matched_attempts": 1},
            "D": {"seen_attempts": 1, "matched_attempts": 1},
            "C": {"seen_attempts": 9, "matched_attempts": 9},
        }
    }

    ordered = dg._v2_order_rs_suits_by_seen_attempts(candidate, rs_entry)
    # H and D tie at 1, preserve original order among ties (H before D)
    assert ordered == ["H", "D", "S", "C"]


def test_v2_order_rs_suits_handles_missing_buckets():
    candidate = ["S", "H", "D", "C"]
    rs_entry = {"buckets": {}}
    ordered = dg._v2_order_rs_suits_by_seen_attempts(candidate, rs_entry)
    assert ordered == candidate