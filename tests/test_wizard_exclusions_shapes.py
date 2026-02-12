from typing import List

from bridge_engine.wizard_flow import _build_exclusion_shapes


class DummySubWithString:
    def __init__(self, shape: str) -> None:
        self.shape_string = shape


class DummySubWithTuple:
    def __init__(self, counts: List[int]) -> None:
        # Simulate something like a suit-length vector.
        self.suit_lengths = counts


class DummySeat:
    def __init__(self, subs):
        self.subprofiles = subs


def test_build_exclusion_shapes_prefers_shape_strings() -> None:
    seat = DummySeat(
        [
            DummySubWithString("5-3-3-2"),
            DummySubWithString("4-4-3-2"),
            DummySubWithString("5-3-3-2"),  # duplicate
        ]
    )

    shapes = _build_exclusion_shapes(seat)

    assert shapes == ["5-3-3-2", "4-4-3-2"]  # unique, order preserved


def test_build_exclusion_shapes_can_use_index() -> None:
    seat = DummySeat(
        [
            DummySubWithString("5-3-3-2"),
            DummySubWithString("4-4-3-2"),
        ]
    )

    shapes_for_first = _build_exclusion_shapes(seat, subprofile_index=0)
    shapes_for_second = _build_exclusion_shapes(seat, subprofile_index=1)

    assert shapes_for_first == ["5-3-3-2"]
    assert shapes_for_second == ["4-4-3-2"]


def test_build_exclusion_shapes_handles_tuple_lengths() -> None:
    seat = DummySeat(
        [
            DummySubWithTuple([6, 3, 2, 2]),
        ]
    )

    shapes = _build_exclusion_shapes(seat)

    assert shapes == ["6-3-2-2"]


def test_build_exclusion_shapes_gracefully_handles_missing_attrs() -> None:
    class WeirdSub:
        pass

    seat = DummySeat([WeirdSub()])

    shapes = _build_exclusion_shapes(seat)

    # No crash, just "no shapes found".
    assert shapes == []