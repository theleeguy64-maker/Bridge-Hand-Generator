"""
Tests for LIN splitting and renumbering utilities in lin_tools.py.

Covers:
  - _split_lin_into_boards() — splitting LIN text into per-board chunks
  - _renumber_boards() — sequential board renumbering
"""

from __future__ import annotations

from bridge_engine.lin_tools import _split_lin_into_boards, _renumber_boards


# ===================================================================
# _split_lin_into_boards
# ===================================================================


class TestSplitLinIntoBoards:
    """Tests for _split_lin_into_boards."""

    def test_single_board(self):
        """Single board produces a 1-element list."""
        text = "qx|o1|ah|Board 1|md|..."
        result = _split_lin_into_boards(text)
        assert len(result) == 1
        assert result[0].startswith("qx|")
        assert "Board 1" in result[0]

    def test_multiple_boards(self):
        """Multiple boards are split correctly."""
        text = "qx|o1|ah|Board 1|md|data1\nqx|o2|ah|Board 2|md|data2\nqx|o3|ah|Board 3|md|data3"
        result = _split_lin_into_boards(text)
        assert len(result) == 3
        assert "Board 1" in result[0]
        assert "Board 2" in result[1]
        assert "Board 3" in result[2]

    def test_each_chunk_has_qx_prefix(self):
        """Every chunk starts with 'qx|' (re-added after split)."""
        text = "qx|o1|ah|Board 1|\nqx|o2|ah|Board 2|"
        result = _split_lin_into_boards(text)
        for chunk in result:
            assert chunk.startswith("qx|")

    def test_empty_string(self):
        """Empty input returns empty list."""
        assert _split_lin_into_boards("") == []

    def test_no_qx_delimiter(self):
        """Input without 'qx|' still produces a chunk (text is non-empty after split)."""
        result = _split_lin_into_boards("just some text")
        assert len(result) == 1
        assert result[0] == "qx|just some text"

    def test_whitespace_between_boards(self):
        """Extra whitespace between boards is handled."""
        text = "qx|o1|ah|Board 1|  \n  qx|o2|ah|Board 2|  "
        result = _split_lin_into_boards(text)
        assert len(result) == 2


# ===================================================================
# _renumber_boards
# ===================================================================


class TestRenumberBoards:
    """Tests for _renumber_boards."""

    def test_renumber_from_1(self):
        """Default renumbering starts at 1."""
        boards = [
            "qx|o5|ah|Board 5|md|data",
            "qx|o9|ah|Board 9|md|data",
        ]
        result = _renumber_boards(boards)
        assert "Board 1" in result[0]
        assert "Board 2" in result[1]

    def test_renumber_from_custom_start(self):
        """start_at parameter controls the starting board number."""
        boards = [
            "qx|o1|ah|Board 1|md|data",
            "qx|o2|ah|Board 2|md|data",
        ]
        result = _renumber_boards(boards, start_at=10)
        assert "Board 10" in result[0]
        assert "Board 11" in result[1]

    def test_qx_tag_renumbered(self):
        """The qx|oN| container tag is also renumbered."""
        boards = ["qx|o5|ah|Board 5|md|data"]
        result = _renumber_boards(boards, start_at=1)
        assert "qx|o1|" in result[0]
        assert "qx|o5|" not in result[0]

    def test_empty_list(self):
        """Empty input returns empty output."""
        assert _renumber_boards([]) == []

    def test_preserves_non_label_content(self):
        """Content other than Board labels and qx tags is preserved."""
        boards = ["qx|o3|ah|Board 3|md|3SAKQJ2H53DT94C85,S86HAK6DAJ82CKQ97|"]
        result = _renumber_boards(boards, start_at=1)
        assert "md|3SAKQJ2H53DT94C85,S86HAK6DAJ82CKQ97|" in result[0]

    def test_only_first_board_label_replaced(self):
        """Only the first 'Board N' occurrence is replaced per chunk."""
        boards = ["qx|o1|ah|Board 1|sv|Board 1 notes|"]
        result = _renumber_boards(boards, start_at=7)
        # First "Board 1" becomes "Board 7", second stays "Board 1"
        assert result[0].count("Board 7") == 1
        assert result[0].count("Board 1") == 1
