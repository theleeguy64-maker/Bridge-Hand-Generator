from __future__ import annotations

from pathlib import Path
import random
import re
from typing import Iterable, List
from typing import Iterable

from collections import defaultdict
from typing import Dict, List, Sequence, Mapping


import re

# Match names like:
#   Lee_Opps_Open_&_Our_TO_Dbl_BBO_1128_2008
#   Lee_Opps_Open_&_Our_TO_Dbl_BBO_1209_0922
#   Lee_Our 1 Major & Opponents Interrference_BBO_1130_0844_FIXED
_BBO_PATTERN = re.compile(
    r"^(?P<prefix>.+?)_BBO_\d{4}_\d{4}(?:_FIXED)?$"
)


def logical_lin_key(path: Path) -> str:
    """
    Return a 'logical' key for grouping LIN files that belong to the
    same teaching set.

    For names like:
        Lee_Opps_Open_&_Our_TO_Dbl_BBO_1128_2008.lin
        Lee_Opps_Open_&_Our_TO_Dbl_BBO_1209_0922.lin

    both map to:
        'Lee_Opps_Open_&_Our_TO_Dbl'

    so we keep only the latest one in that group.
    """
    stem = path.stem  # filename without .lin

    m = _BBO_PATTERN.match(stem)
    if m:
        return m.group("prefix")

    # Fallback: strip trailing numeric block(s), just in case
    # e.g. Foo_1209_0922 -> Foo
    stem = re.sub(r"_\d{4}_\d{4}(?:_FIXED)?$", "", stem)
    stem = re.sub(r"_\d{4,}$", "", stem)
    return stem

def select_latest_per_group(paths: Iterable[Path]) -> list[Path]:
    """
    Given an iterable of .lin Paths, group them by logical_lin_key,
    and return only the latest (lexicographically largest filename)
    from each group.

    Example: if you have both
      Lee_Opps_Open_&_Our_TO_Dbl_BBO_1128_2008.lin
      Lee_Opps_Open_&_Our_TO_Dbl_BBO_1209_0922.lin
    only the 1209_0922 file is returned.
    """
    groups: dict[str, Path] = {}

    for p in paths:
        key = logical_lin_key(p)
        current = groups.get(key)
        # Keep the lexicographically-largest name as "latest"
        if current is None or p.name > current.name:
            groups[key] = p

    # Return a stable list (sorted by filename for nicer menus/tests)
    return sorted(groups.values(), key=lambda p: p.name)


def group_lin_files_by_scenario(paths: Sequence[Path]) -> Dict[str, List[Path]]:
    """
    Group LIN files by their logical 'scenario key'.

    Returns:
        dict: {scenario_key -> [Path, Path, ...]}
    """
    groups: Dict[str, List[Path]] = defaultdict(list)
    for p in paths:
        groups[logical_lin_key(p)].append(p)
    return dict(groups)


def latest_lin_file_per_scenario(
    groups: Mapping[str, Sequence[Path]],
) -> Dict[str, Path]:
    """
    From grouped LIN files, pick the latest (by mtime) for each scenario.

    Returns:
        dict: {scenario_key -> latest Path}
    """
    latest: Dict[str, Path] = {}
    for key, files in groups.items():
        if not files:
            continue
        latest[key] = max(files, key=lambda p: p.stat().st_mtime)
    return latest


def _split_lin_into_boards(text: str) -> List[str]:
    """
    Split a LIN file into per-board chunks.

    This assumes standard BBO style where each board starts with 'qx|'.
    If your encoder uses a different delimiter, tweak this function.
    """
    parts = text.split("qx|")
    boards: List[str] = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        # Re-add the 'qx|' prefix we split on
        boards.append("qx|" + part)
    return boards


_BOARD_AH_RE = re.compile(r"ah\|Board\s+\d+\|")


def _renumber_boards(boards: Iterable[str], start_at: int = 1) -> List[str]:
    """
    Renumber the 'Board N' annotations in each board chunk so they are
    sequential starting from start_at.

    This only touches the 'ah|Board N|' tag (if present) and leaves
    everything else unchanged.
    """
    renumbered: List[str] = []
    num = start_at
    for board in boards:
        def repl(_match: re.Match) -> str:
            return f"ah|Board {num}|"

        new_board = _BOARD_AH_RE.sub(repl, board)
        renumbered.append(new_board)
        num += 1
    return renumbered


def combine_lin_files(
    input_paths: List[Path],
    output_path: Path,
    seed: int | None = None,
    weights: List[float] | None = None,
) -> int:
    """
    Combine multiple LIN files into a single LIN file.

    Strategy:
      * Each input file is parsed into an ordered list of boards.
      * We keep an index per file.
      * While any file has remaining boards:
          - randomly choose one of the files that still has boards
            (optionally weighted by the given per-file weights)
          - take its next board (preserving within-file order)
      * Finally, renumber the boards so they are 1..N in order and
        write them to output_path.

    The optional `weights` parameter is a list of non-negative numbers
    (one per input file). They are treated as relative weights; they do
    not need to sum to 1 or 100. If `weights` is None, has the wrong
    length, or all weights are zero/negative, we fall back to equal
    weighting across files.
    """
    rng = random.Random(seed)

    # Load boards per file
    per_file_boards: List[List[str]] = []
    for path in input_paths:
        text = path.read_text(encoding="utf-8")
        boards = _split_lin_into_boards(text)
        per_file_boards.append(boards)

    # Current index for each file
    indices = [0 for _ in per_file_boards]

    # Normalise / validate weights
    file_weights: List[float]
    if not input_paths:
        return 0

    if weights is None or len(weights) != len(input_paths):
        # Default: equal weights
        file_weights = [1.0 for _ in input_paths]
    else:
        cleaned: List[float] = []
        for w in weights:
            try:
                w_f = float(w)
            except (TypeError, ValueError):
                w_f = 0.0
            if w_f < 0.0:
                w_f = 0.0
            cleaned.append(w_f)
        if all(w <= 0.0 for w in cleaned):
            # All zero/negative → fall back to equal weighting
            file_weights = [1.0 for _ in input_paths]
        else:
            file_weights = cleaned

    def _weighted_choice_index(available_indices: List[int]) -> int:
        """
        Choose a file index from `available_indices` using file_weights.

        If the total active weight is <= 0 (should not happen after the
        cleaning above), fall back to uniform random choice.
        """
        active_weights = [file_weights[i] for i in available_indices]
        total = sum(active_weights)
        if total <= 0.0:
            return rng.choice(available_indices)

        r = rng.random() * total
        accum = 0.0
        for idx, w in zip(available_indices, active_weights):
            accum += w
            if r < accum:
                return idx
        # Fallback due to floating-point edge cases
        return available_indices[-1]

    combined: List[str] = []

    # Files that still have remaining boards
    remaining_files = [i for i, boards in enumerate(per_file_boards) if boards]

    while remaining_files:
        fi = _weighted_choice_index(remaining_files)
        bi = indices[fi]
        combined.append(per_file_boards[fi][bi])
        indices[fi] += 1

        # If we exhausted this file, remove it from the pool
        if indices[fi] >= len(per_file_boards[fi]):
            remaining_files = [i for i in remaining_files if i != fi]

    # Renumber Board 1..N in order
    combined = _renumber_boards(combined, start_at=1)

    # Write out as a single LIN file; blank lines between boards for readability
    output_path.write_text("\n\n".join(combined) + "\n", encoding="utf-8")

    return len(combined)
    
def run_lin_combiner() -> None:
    """
    Interactive LIN combiner used by orchestrator.main_menu().

    - Asks for a directory containing .lin files (default: out/lin)
    - Groups files by logical name (using logical_lin_key)
    - For each group, keeps only the latest file
    - Lets the user choose which of these latest files to include
    - Calls combine_lin_files(...) to create one combined LIN file
    """

    print("\n=== LIN combiner ===")

    # 1) Ask for directory (default: out/lin)
    base_dir_str = input("Directory containing .lin files [out/lin]: ").strip() or "out/lin"
    base_dir = Path(base_dir_str).expanduser()

    if not base_dir.is_dir():
        print(f"ERROR: {base_dir} is not a directory.")
        return

    # 2) Find all .lin files
    all_lin_files = sorted(base_dir.glob("*.lin"))
    if not all_lin_files:
        print(f"No .lin files found in {base_dir}.")
        return

    # 3) Group by logical key and keep only the latest file in each group
    try:
        groups = group_lin_files_by_logical_name(all_lin_files)
    except NameError:
        # Fallback: no grouping helper available, just treat all files as separate
        groups = {f: [f] for f in all_lin_files}

    latest_files = []
    for key, files in groups.items():
        # "Latest" by modification time; if that ever fails, fall back to name sort
        try:
            latest = max(files, key=lambda p: p.stat().st_mtime)
        except Exception:
            latest = sorted(files)[-1]
        latest_files.append(latest)

    latest_files = select_latest_per_group(all_lin_files)

    # 4) Show list of candidate files (latest per logical group)
    print("\nAvailable LIN files (latest per logical group):")
    for idx, p in enumerate(latest_files, start=1):
        print(f"  {idx}) {p.name}")

    # 5) Let user choose which ones to include
    raw = input(
        "Enter numbers to include (exact format x,y,z, e.g. 1,3,7) or press Enter to include ALL: "
        "or press Enter to include ALL: "
    ).strip()

    if not raw:
        chosen_files = latest_files
    else:
        indices = set()
        for part in raw.replace(" ", "").split(","):
            if not part:
                continue
            try:
                i = int(part)
            except ValueError:
                print(f"Ignoring invalid entry: {part!r}")
                continue
            if 1 <= i <= len(latest_files):
                indices.add(i)
            else:
                print(f"Ignoring out-of-range entry: {part!r}")

        if not indices:
            print("No valid selections made; aborting.")
            return

        chosen_files = [latest_files[i - 1] for i in sorted(indices)]

    print("\nYou chose these files:")
    for p in chosen_files:
        print(f"  - {p.name}")

    # 5b) Optional weighted selection (F4)
    file_weights: List[float] | None = None
    if chosen_files:
        use_weights = input(
            "\nUse weighted selection by source file? [y/N]: "
        ).strip().lower()
        if use_weights.startswith("y"):
            print(
                "Enter relative weights for each file "
                "(they do NOT need to sum to 100)."
            )
            file_weights = []
            for p in chosen_files:
                while True:
                    raw_w = input(f"  Weight for {p.name} [1]: ").strip()
                    if not raw_w:
                        raw_w = "1"
                    try:
                        w = float(raw_w)
                    except ValueError:
                        print(f"    Invalid number {raw_w!r}; please enter a numeric weight.")
                        continue
                    if w < 0.0:
                        print("    Weight must be non-negative.")
                        continue
                    file_weights.append(w)
                    break

    # 6) Ask for output filename
    default_output = "combined.lin"
    out_name = input(f"\nOutput LIN filename [{default_output}]: ").strip() or default_output
    output_path = base_dir / out_name

    # 7) Optional seed
    seed_str = input("Random seed for shuffling (blank for none): ").strip()
    seed = None
    if seed_str:
        try:
            seed = int(seed_str)
        except ValueError:
            print("Seed must be an integer; ignoring and proceeding without a seed.")
            seed = None

    # 8) Combine
    try:
        combine_lin_files(
            input_paths=chosen_files,
            output_path=output_path,
            seed=seed,
            file_weights=file_weights,
        )
    except Exception as exc:
        print(f"\nERROR: failed to combine LIN files: {exc}")
        return

    print(f"\nCombined {len(chosen_files)} LIN files into: {output_path}")
    print("Deal numbers have been renumbered starting from 1.")