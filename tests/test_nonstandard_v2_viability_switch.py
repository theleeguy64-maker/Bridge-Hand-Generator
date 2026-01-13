from bridge_engine import deal_generator as dg


def test_piece6_explore_vs_exploit_orders_differ():
    orig = ["S", "H"]

    # Arrange a situation where:
    # - Explore (least-seen) should pick H first (seen=1 vs 10)
    # - Exploit (success-rate) should pick S first (9/10 vs 0/1)
    rs_entry = {
        "buckets": {
            "S": {"seen_attempts": 10, "matched_attempts": 9},
            "H": {"seen_attempts": 1, "matched_attempts": 0},
        }
    }

    explore = sorted(
        orig,
        key=lambda s: (
            int(rs_entry["buckets"].get(s, {}).get("seen_attempts", 0) or 0),
            orig.index(s),
        ),
    )
    exploit = dg._v2_order_rs_suits_weighted(orig, rs_entry)

    assert explore[0] == "H"
    assert exploit[0] == "S"