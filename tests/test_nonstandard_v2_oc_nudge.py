from types import SimpleNamespace

from bridge_engine import deal_generator as dg


def test_piece5_oc_nudge_tries_alternate_subprofiles_and_updates_choice():
    oc1 = SimpleNamespace(opponents_contingent_suit_constraint=object())
    oc2 = SimpleNamespace(opponents_contingent_suit_constraint=object())

    seat_profile = SimpleNamespace(subprofiles=[oc1, oc2])
    constructive_mode = {"nonstandard_v2": True}

    calls = []

    def match_fn(alt_sub, alt_i0):
        calls.append((alt_sub, alt_i0))
        return (alt_i0 == 1), None  # succeed only for index 1

    matched, chosen_rs, chosen_sub, idx0 = dg._v2_oc_nudge_try_alternates(
        constructive_mode=constructive_mode,
        seat_profile=seat_profile,
        chosen_sub=oc1,
        idx0=0,
        match_fn=match_fn,
    )

    assert matched is True
    assert chosen_rs is None
    assert chosen_sub is oc2
    assert idx0 == 1
    assert calls == [(oc2, 1)]


def test_piece5_oc_nudge_noop_when_not_v2():
    oc1 = SimpleNamespace(opponents_contingent_suit_constraint=object())
    oc2 = SimpleNamespace(opponents_contingent_suit_constraint=object())

    seat_profile = SimpleNamespace(subprofiles=[oc1, oc2])
    constructive_mode = {"nonstandard_v2": False}

    def match_fn(alt_sub, alt_i0):
        raise AssertionError("should not be called")

    matched, chosen_rs, chosen_sub, idx0 = dg._v2_oc_nudge_try_alternates(
        constructive_mode=constructive_mode,
        seat_profile=seat_profile,
        chosen_sub=oc1,
        idx0=0,
        match_fn=match_fn,
    )

    assert matched is False
    assert chosen_rs is None
    assert chosen_sub is oc1
    assert idx0 == 0