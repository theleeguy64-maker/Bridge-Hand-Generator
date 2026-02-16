# tests/test_match_standard_classification.py
"""
Tests for HCP vs shape failure classification in _match_standard().

Item 1 of Priority 1: Verify that _match_standard() correctly classifies
failures as "hcp" or "shape" so the constructive helper system can make
informed decisions.
"""

from types import SimpleNamespace

from bridge_engine.seat_viability import _match_standard, _compute_suit_analysis


def _make_standard_constraints(
    *,
    min_cards=(0, 0, 0, 0),
    max_cards=(13, 13, 13, 13),
    min_hcp=(0, 0, 0, 0),
    max_hcp=(10, 10, 10, 10),
    total_min_hcp=0,
    total_max_hcp=37,
):
    """
    Build a StandardSuitConstraints-like object for testing.
    Uses duck-typing via SimpleNamespace.
    """
    return SimpleNamespace(
        spades=SimpleNamespace(
            min_cards=min_cards[0],
            max_cards=max_cards[0],
            min_hcp=min_hcp[0],
            max_hcp=max_hcp[0],
        ),
        hearts=SimpleNamespace(
            min_cards=min_cards[1],
            max_cards=max_cards[1],
            min_hcp=min_hcp[1],
            max_hcp=max_hcp[1],
        ),
        diamonds=SimpleNamespace(
            min_cards=min_cards[2],
            max_cards=max_cards[2],
            min_hcp=min_hcp[2],
            max_hcp=max_hcp[2],
        ),
        clubs=SimpleNamespace(
            min_cards=min_cards[3],
            max_cards=max_cards[3],
            min_hcp=min_hcp[3],
            max_hcp=max_hcp[3],
        ),
        total_min_hcp=total_min_hcp,
        total_max_hcp=total_max_hcp,
    )


def _make_hand(*cards):
    """Convert card strings like 'AS', 'KH' to the format expected by _compute_suit_analysis."""
    return list(cards)


# ---------------------------------------------------------------------------
# Success cases
# ---------------------------------------------------------------------------


def test_match_standard_success_returns_none_reason():
    """A matching hand returns (True, None) - no failure reason."""
    # Hand: 4 spades (AKQJ=10 HCP), 4 hearts, 3 diamonds, 2 clubs = 13 cards, 10 HCP
    hand = _make_hand(
        "AS",
        "KS",
        "QS",
        "JS",  # 4 spades, 10 HCP
        "2H",
        "3H",
        "4H",
        "5H",  # 4 hearts, 0 HCP
        "2D",
        "3D",
        "4D",  # 3 diamonds, 0 HCP
        "2C",
        "3C",  # 2 clubs, 0 HCP
    )
    analysis = _compute_suit_analysis(hand)
    std = _make_standard_constraints(
        min_cards=(3, 3, 2, 2),
        max_cards=(5, 5, 5, 5),
        total_min_hcp=8,
        total_max_hcp=15,
    )

    matched, fail_reason = _match_standard(analysis, std)

    assert matched is True
    assert fail_reason is None


# ---------------------------------------------------------------------------
# HCP failure cases
# ---------------------------------------------------------------------------


def test_match_standard_fails_total_hcp_too_low():
    """Hand with too few total HCP returns (False, 'hcp')."""
    # All low cards = 0 HCP
    hand = _make_hand(
        "2S",
        "3S",
        "4S",
        "5S",
        "2H",
        "3H",
        "4H",
        "5H",
        "2D",
        "3D",
        "4D",
        "2C",
        "3C",
    )
    analysis = _compute_suit_analysis(hand)
    std = _make_standard_constraints(total_min_hcp=10, total_max_hcp=37)

    matched, fail_reason = _match_standard(analysis, std)

    assert matched is False
    assert fail_reason == "hcp"


def test_match_standard_fails_total_hcp_too_high():
    """Hand with too many total HCP returns (False, 'hcp')."""
    # All honors = 36 HCP
    hand = _make_hand(
        "AS",
        "KS",
        "QS",
        "JS",  # 10 HCP
        "AH",
        "KH",
        "QH",
        "JH",  # 10 HCP
        "AD",
        "KD",
        "QD",  # 9 HCP
        "AC",
        "KC",  # 7 HCP = 36 total
    )
    analysis = _compute_suit_analysis(hand)
    std = _make_standard_constraints(total_min_hcp=0, total_max_hcp=20)

    matched, fail_reason = _match_standard(analysis, std)

    assert matched is False
    assert fail_reason == "hcp"


def test_match_standard_fails_suit_hcp_too_high():
    """Hand failing per-suit HCP constraint returns (False, 'hcp')."""
    # 5 spades with 10 HCP in spades, but constraint says max 5 HCP in spades
    hand = _make_hand(
        "AS",
        "KS",
        "QS",
        "JS",
        "TS",  # 5 spades, 10 HCP in spades
        "2H",
        "3H",
        "4H",
        "5H",
        "2D",
        "3D",
        "2C",
        "3C",
    )
    analysis = _compute_suit_analysis(hand)
    std = _make_standard_constraints(
        max_hcp=(5, 10, 10, 10),  # Max 5 HCP in spades
    )

    matched, fail_reason = _match_standard(analysis, std)

    assert matched is False
    assert fail_reason == "hcp"


def test_match_standard_fails_suit_hcp_too_low():
    """Hand failing per-suit min HCP constraint returns (False, 'hcp')."""
    # 4 spades with 0 HCP in spades, but constraint says min 5 HCP in spades
    hand = _make_hand(
        "2S",
        "3S",
        "4S",
        "5S",  # 4 spades, 0 HCP in spades
        "AH",
        "KH",
        "QH",
        "JH",  # 10 HCP in hearts
        "2D",
        "3D",
        "4D",
        "2C",
        "3C",
    )
    analysis = _compute_suit_analysis(hand)
    std = _make_standard_constraints(
        min_hcp=(5, 0, 0, 0),  # Min 5 HCP in spades
    )

    matched, fail_reason = _match_standard(analysis, std)

    assert matched is False
    assert fail_reason == "hcp"


# ---------------------------------------------------------------------------
# Shape failure cases
# ---------------------------------------------------------------------------


def test_match_standard_fails_shape_too_few_cards():
    """Hand with too few cards in a suit returns (False, 'shape')."""
    # Only 1 spade, but need 3+
    hand = _make_hand(
        "AS",  # 1 spade
        "2H",
        "3H",
        "4H",
        "5H",
        "6H",
        "7H",
        "8H",  # 7 hearts
        "2D",
        "3D",  # 2 diamonds
        "2C",
        "3C",
        "4C",  # 3 clubs = 13 total
    )
    analysis = _compute_suit_analysis(hand)
    std = _make_standard_constraints(min_cards=(3, 0, 0, 0))  # Need 3+ spades

    matched, fail_reason = _match_standard(analysis, std)

    assert matched is False
    assert fail_reason == "shape"


def test_match_standard_fails_shape_too_many_cards():
    """Hand with too many cards in a suit returns (False, 'shape')."""
    # 7 spades, but max 5 allowed
    hand = _make_hand(
        "AS",
        "KS",
        "QS",
        "JS",
        "TS",
        "9S",
        "8S",  # 7 spades
        "2H",
        "3H",  # 2 hearts
        "2D",
        "3D",  # 2 diamonds
        "2C",
        "3C",  # 2 clubs = 13 total
    )
    analysis = _compute_suit_analysis(hand)
    std = _make_standard_constraints(max_cards=(5, 13, 13, 13))  # Max 5 spades

    matched, fail_reason = _match_standard(analysis, std)

    assert matched is False
    assert fail_reason == "shape"


# ---------------------------------------------------------------------------
# Priority / ordering cases
# ---------------------------------------------------------------------------


def test_match_standard_hcp_checked_before_shape():
    """
    When both total HCP and shape would fail, HCP is reported first.

    Total HCP is checked before per-suit constraints, so if a hand fails
    the total HCP range, we should get 'hcp' even if shape is also wrong.
    """
    # Hand with 0 HCP AND 7 spades (both wrong)
    hand = _make_hand(
        "2S",
        "3S",
        "4S",
        "5S",
        "6S",
        "7S",
        "8S",  # 7 spades, 0 HCP
        "2H",
        "3H",  # 2 hearts
        "2D",
        "3D",  # 2 diamonds
        "2C",
        "3C",  # 2 clubs
    )
    analysis = _compute_suit_analysis(hand)
    std = _make_standard_constraints(
        total_min_hcp=10,  # Will fail - 0 HCP
        max_cards=(5, 13, 13, 13),  # Would also fail - 7 spades
    )

    matched, fail_reason = _match_standard(analysis, std)

    assert matched is False
    # HCP is checked first, so should report "hcp" not "shape"
    assert fail_reason == "hcp"


def test_match_standard_shape_before_suit_hcp():
    """
    Within per-suit checks, shape (card count) is checked before suit HCP.

    If total HCP passes but both suit shape and suit HCP would fail,
    shape is reported because card count is checked before suit HCP.
    """
    # Hand with:
    # - Total HCP is fine (10 HCP, constraint allows 0-37)
    # - Spades: only 2 cards (need 3+) AND 7 HCP (but max allowed is 5)
    hand = _make_hand(
        "AS",
        "KS",  # 2 spades, 7 HCP (A=4, K=3)
        "2H",
        "3H",
        "4H",
        "5H",
        "6H",  # 5 hearts, 0 HCP
        "2D",
        "3D",
        "4D",  # 3 diamonds, 0 HCP
        "2C",
        "3C",
        "4C",  # 3 clubs, 0 HCP = 13 total, 7 HCP
    )
    analysis = _compute_suit_analysis(hand)
    std = _make_standard_constraints(
        min_cards=(3, 0, 0, 0),  # Need 3+ spades - will fail (only 2)
        max_hcp=(5, 10, 10, 10),  # Max 5 HCP in spades - would also fail (7 HCP)
    )

    matched, fail_reason = _match_standard(analysis, std)

    assert matched is False
    # Shape (card count) is checked before suit HCP, so should report "shape"
    assert fail_reason == "shape"
