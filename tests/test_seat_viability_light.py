# tests/test_seat_viability_light.py

from types import SimpleNamespace

from bridge_engine.seat_viability import _subprofile_is_viable_light


def _make_dummy_subprofile(
    *,
    min_cards=(0, 0, 0, 0),
    max_cards=(13, 13, 13, 13),
    total_min_hcp=0,
    total_max_hcp=37,
):
    """
    Build a minimal dummy 'subprofile' object with the attributes that
    _subprofile_is_viable_light() actually touches.

    We don't depend on the real SubProfile / Standard classes here –
    just duck-typing via SimpleNamespace.
    """
    spades_min, hearts_min, diamonds_min, clubs_min = min_cards
    spades_max, hearts_max, diamonds_max, clubs_max = max_cards

    std = SimpleNamespace(
        spades=SimpleNamespace(min_cards=spades_min, max_cards=spades_max),
        hearts=SimpleNamespace(min_cards=hearts_min, max_cards=hearts_max),
        diamonds=SimpleNamespace(min_cards=diamonds_min, max_cards=diamonds_max),
        clubs=SimpleNamespace(min_cards=clubs_min, max_cards=clubs_max),
        total_min_hcp=total_min_hcp,
        total_max_hcp=total_max_hcp,
    )

    # SubProfile duck-type with a .standard attribute
    sub = SimpleNamespace(standard=std)
    return sub


def test_subprofile_is_viable_light_ok():
    """
    Baseline: a standard with feasible suit and HCP ranges is accepted.
    """
    sub = _make_dummy_subprofile(
        min_cards=(0, 0, 0, 0),
        max_cards=(13, 13, 13, 13),
        total_min_hcp=0,
        total_max_hcp=37,
    )

    ok, reason = _subprofile_is_viable_light(sub, return_reason=True)
    assert ok is True
    assert reason == "ok"


def test_subprofile_is_viable_light_too_many_min_cards():
    """
    If the sum of minimum cards in the four suits exceeds 13,
    the subprofile must be rejected.
    """
    # 5+4+3+2 = 14 > 13
    sub = _make_dummy_subprofile(
        min_cards=(5, 4, 3, 2),
        max_cards=(13, 13, 13, 13),
    )

    ok, reason = _subprofile_is_viable_light(sub, return_reason=True)
    assert ok is False
    assert "mins sum to" in reason
    assert "> 13" in reason


def test_subprofile_is_viable_light_too_few_max_cards():
    """
    If the sum of maximum cards in the four suits is < 13,
    the subprofile must be rejected.
    """
    # Max total 12 < 13
    sub = _make_dummy_subprofile(
        min_cards=(0, 0, 0, 0),
        max_cards=(3, 3, 3, 3),
    )

    ok, reason = _subprofile_is_viable_light(sub, return_reason=True)
    assert ok is False
    assert "maxs sum to" in reason
    assert "< 13" in reason


def test_subprofile_is_viable_light_min_hcp_too_high():
    """
    A 13-card hand cannot guarantee more than 37 HCP; enforcing a
    higher minimum should be rejected.
    """
    sub = _make_dummy_subprofile(
        total_min_hcp=38,  # > 37 -> invalid
    )

    ok, reason = _subprofile_is_viable_light(sub, return_reason=True)
    assert ok is False
    assert "total_min_hcp" in reason
    assert "> 37" in reason


def test_subprofile_is_viable_light_max_hcp_too_low():
    """
    Negative total_max_hcp should be rejected as infeasible.
    """
    sub = _make_dummy_subprofile(
        total_max_hcp=-1,
    )

    ok, reason = _subprofile_is_viable_light(sub, return_reason=True)
    assert ok is False
    assert "total_max_hcp" in reason
    assert "< 0" in reason