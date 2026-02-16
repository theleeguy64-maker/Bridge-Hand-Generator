# test/test_weighted_lin_combiner.py

from pathlib import Path
from bridge_engine.lin_tools import combine_lin_files


def test_combiner_renumbers_boards_sequentially(tmp_path: Path) -> None:
    """
    The LIN combiner should renumber boards sequentially 1..N in the
    *output file*, regardless of the original board numbers in the
    source LINs.
    """
    file1 = tmp_path / "a.lin"
    file2 = tmp_path / "b.lin"
    out_file = tmp_path / "combined.lin"

    # Minimal-but-valid-ish LIN fragments with weird board numbers.
    # The combiner only cares that there is a "Board <number>" label
    # inside each board string; full LIN fidelity isn't needed here.
    file1.write_text("qx|Board 7|foo|\n")
    file2.write_text("qx|Board 42|bar|\n")

    # Use the real combiner API: inputs + output path.
    combine_lin_files([file1, file2], out_file)

    combined = out_file.read_text()

    # New labels must be 1..N
    assert "Board 1" in combined
    assert "Board 2" in combined

    # Old labels must not survive
    assert "Board 7" not in combined
    assert "Board 42" not in combined
