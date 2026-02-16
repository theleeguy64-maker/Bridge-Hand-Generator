# tests/test_lin_tools_grouping.py

from pathlib import Path

from bridge_engine import lin_tools


def test_logical_lin_key_groups_bbo_variants_together() -> None:
    """
    Files that differ only by the BBO date/time (and optional _FIXED)
    should share the same logical key.
    """
    p_old = Path("Lee_Opps_Open_&_Our_TO_Dbl_BBO_1128_2008.lin")
    p_new = Path("Lee_Opps_Open_&_Our_TO_Dbl_BBO_1209_0922.lin")
    p_fix = Path("Lee_Defense to 3 Weak 2s_BBO_1130_0844_FIXED.lin")
    p_new2 = Path("Lee_Defense to 3 Weak 2s_BBO_1209_0922.lin")

    k_old = lin_tools.logical_lin_key(p_old)
    k_new = lin_tools.logical_lin_key(p_new)
    k_fix = lin_tools.logical_lin_key(p_fix)
    k_new2 = lin_tools.logical_lin_key(p_new2)

    # Same scenario → same key
    assert k_old == k_new
    assert k_fix == k_new2

    # Different scenarios → different keys
    assert k_old != k_fix


def test_logical_lin_key_non_bbo_names_fallback() -> None:
    """
    Non-BBO-style names should still produce a stable logical key.
    We don't care exactly what it is, just that it's deterministic.
    """
    p1 = Path("RandomTrainingSet_01.lin")
    p2 = Path("RandomTrainingSet_01_COPY.lin")

    k1 = lin_tools.logical_lin_key(p1)
    k2 = lin_tools.logical_lin_key(p2)

    # They are different filenames, so keys may differ
    # but they must be consistent (function doesn't crash).
    assert isinstance(k1, str)
    assert isinstance(k2, str)
    assert k1  # non-empty
    assert k2  # non-empty


def test_select_latest_per_group_picks_latest_for_each_scenario() -> None:
    """
    Given multiple LIN files per logical scenario, we should keep
    only the latest (lexicographically largest) filename in each group.
    """
    # Opps Open & Our TO Dbl
    opps_old = Path("Lee_Opps_Open_&_Our_TO_Dbl_BBO_1128_2008.lin")
    opps_new = Path("Lee_Opps_Open_&_Our_TO_Dbl_BBO_1209_0922.lin")

    # Ops interference over our 1NT
    ops_old = Path("Lee_Ops interference over our 1NT_BBO_1128_2015.lin")
    ops_new = Path("Lee_Ops interference over our 1NT_BBO_1209_0923.lin")

    # Our 1 Major & Opponents Interference
    maj_old = Path("Lee_Our 1 Major & Opponents Interrference_BBO_1130_0844_FIXED.lin")
    maj_new = Path("Lee_Our 1 Major & Opponents Interrference_BBO_1209_0923.lin")

    # A single-file scenario (no alternative)
    single = Path("Lee_Responding with a Major to 1NT Opening_BBO_1130_0844_FIXED.lin")

    all_paths = [
        opps_old,
        opps_new,
        ops_old,
        ops_new,
        maj_old,
        maj_new,
        single,
    ]

    selected = lin_tools.select_latest_per_group(all_paths)
    selected_names = {p.name for p in selected}

    # We should see ONLY the latest of each pair, plus the single
    assert "Lee_Opps_Open_&_Our_TO_Dbl_BBO_1209_0922.lin" in selected_names
    assert "Lee_Opps_Open_&_Our_TO_Dbl_BBO_1128_2008.lin" not in selected_names

    assert "Lee_Ops interference over our 1NT_BBO_1209_0923.lin" in selected_names
    assert "Lee_Ops interference over our 1NT_BBO_1128_2015.lin" not in selected_names

    assert "Lee_Our 1 Major & Opponents Interrference_BBO_1209_0923.lin" in selected_names
    assert "Lee_Our 1 Major & Opponents Interrference_BBO_1130_0844_FIXED.lin" not in selected_names

    # The lone scenario must remain
    assert "Lee_Responding with a Major to 1NT Opening_BBO_1130_0844_FIXED.lin" in selected_names

    # We started with 7, but only 4 logical scenarios:
    #   - Opps Open & Our TO Dbl  → latest
    #   - Ops interference over 1NT → latest
    #   - Our 1 Major & Opponents Interference → latest
    #   - Responding with a Major → single
    assert len(selected_names) == 4


def test_select_latest_per_group_is_stable_for_singletons() -> None:
    """
    If each path is already in a unique group, select_latest_per_group
    should effectively be a no-op (modulo ordering).
    """
    paths = [
        Path("A_Scenario_BBO_1111_0001.lin"),
        Path("B_Scenario_BBO_1111_0001.lin"),
        Path("C_Scenario_BBO_1111_0001.lin"),
    ]

    selected = lin_tools.select_latest_per_group(paths)

    # Same three names, just maybe different order
    assert {p.name for p in selected} == {p.name for p in paths}
