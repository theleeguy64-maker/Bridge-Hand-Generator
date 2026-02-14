from __future__ import annotations

import random
import re
from pathlib import Path
from typing import Dict, Iterable, List

# ---------------------------------------------------------------------------
# Compiled regex patterns (all in one place for easy auditing)
# ---------------------------------------------------------------------------

# Match full BBO filenames: Lee_Profile_BBO_1128_2008 (optional _FIXED suffix)
_BBO_PATTERN = re.compile(
    r"^(?P<prefix>.+?)_BBO_\d{4}_\d{4}(?:_FIXED)?$"
)

# Fallback patterns for stripping trailing timestamps from LIN stems
_BBO_TIMESTAMP_SUFFIX_RE = re.compile(r"_\d{4}_\d{4}(?:_FIXED)?$")
_TRAILING_NUMBERS_RE = re.compile(r"_\d{4,}$")

# Match "Board 1", "Board 12", etc. in LIN content (case-insensitive)
_BOARD_LABEL_RE = re.compile(r"Board\s+\d+", re.IGNORECASE)


def _pretty_lin_profile_label(path: Path) -> str:
    """
    Derive a human-friendly 'profile name' label from a LIN filename.

    Expected pattern (current generator output):
        Author_Profile Name_BBO_YYYY_HHMM.lin

    We strip:
      • the leading 'Author_' chunk
      • the trailing '_BBO_...' timestamp suffix
    and return just 'Profile Name'.

    If the pattern doesn't match, fall back to the bare stem.
    """
    stem = path.stem  # e.g. 'Lee_1 major then interference_BBO_1128_2008'

    # Strip trailing BBO timestamp suffix, if present
    if "_BBO_" in stem:
        stem, _ = stem.split("_BBO_", 1)

    # Now stem is e.g. 'Lee_1 major then interference'
    parts = stem.split("_", 1)
    if len(parts) == 2:
        # Drop author → return the rest as profile label
        return parts[1].strip()

    # Fallback for unexpected patterns
    return stem.strip()


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
    stem = _BBO_TIMESTAMP_SUFFIX_RE.sub("", stem)
    stem = _TRAILING_NUMBERS_RE.sub("", stem)
    return stem


def select_latest_per_group(paths: Iterable[Path]) -> List[Path]:
    """
    Given an iterable of .lin Paths, group them by logical_lin_key,
    and return only the latest (lexicographically largest filename)
    from each group.

    Example: if you have both
      Lee_Opps_Open_&_Our_TO_Dbl_BBO_1128_2008.lin
      Lee_Opps_Open_&_Our_TO_Dbl_BBO_1209_0922.lin
    only the 1209_0922 file is returned.
    """
    groups: Dict[str, Path] = {}

    for p in paths:
        key = logical_lin_key(p)
        current = groups.get(key)
        # Keep the lexicographically-largest name as "latest"
        if current is None or p.name > current.name:
            groups[key] = p

    # Return a stable list (sorted by filename for nicer menus/tests)
    return sorted(groups.values(), key=lambda p: p.name)


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


def _renumber_boards(boards: List[str], start_at: int = 1) -> List[str]:
    """
    Given a list of raw board strings, rewrite the first "Board <n>"
    label in each one so that the boards are numbered sequentially
    starting at `start_at`.

    This is intentionally liberal: many LIN producers put the label
    inside an 'ah|' tag (e.g. 'ah|Board 13|'), but others may not.
    We just rewrite the first 'Board <number>' we see in each board.
    """
    renumbered: List[str] = []
    num = start_at

    for board in boards:
        label = f"Board {num}"

        # Replace the first "Board <number>" if present.
        def repl(_match: re.Match) -> str:  # type: ignore[override]
            return label

        new_board, count = _BOARD_LABEL_RE.subn(repl, board, count=1)

        # If we somehow didn't find a Board label at all, just leave
        # the board unchanged rather than risking mangling the LIN.
        if count == 0:
            new_board = board

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
    if not input_paths:
        return 0

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
    
    
def combine_lin_files_interactive() -> None:
    """
    CLI entrypoint for the LIN combiner, used by the Admin menu.

    This wraps the existing interactive LIN-combiner flow so that:
      • orchestrator.admin_menu() can call a single function,
      • tests for the combiner can keep using their current APIs.
    """
    run_lin_combiner()
    
    
def run_lin_combiner() -> None:
    """
    Interactive LIN combiner used by the Admin menu.

    - Asks for a directory containing .lin files (default: out/lin)
    - Groups files by logical name (using select_latest_per_group)
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

    # 3) Latest file per logical group
    # (select_latest_per_group is your existing helper)
    latest_files = select_latest_per_group(all_lin_files)

    # Require at least 2 candidate files for combining
    if len(latest_files) < 2:
        print(
            f"\nFound only {len(latest_files)} eligible LIN file(s) in {base_dir}. "
            "You need at least 2 to run the combiner."
        )
        return

    # 4 + 5) Show list and let user choose (must select at least 2)
    while True:
        print("\nAvailable LIN files (latest per logical group):")
        for idx, p in enumerate(latest_files, start=1):
            print(f"  {idx}) {p.name}")

        raw = input(
            "\nEnter numbers to include (exact format x,y,z, e.g. 1,3,7) "
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
                print("No valid selections made; please try again.")
                continue

            chosen_files = [latest_files[i - 1] for i in sorted(indices)]

        if len(chosen_files) < 2:
            print("You must select at least 2 files to combine. Please choose again.")
            continue

        break

    print("\nYou chose these files:")
    for p in chosen_files:
        # You already have a helper that can show a nice label; if it
        # currently uses filename-only, we can improve that later.
        label = _pretty_lin_profile_label(p)
        print(f"  - {label}")

    # 5b) Optional weighted selection (F4)
    # chosen_files is guaranteed non-empty (>= 2 items) by the selection loop above.
    file_weights: List[float] | None = None
    use_weights = input(
        "\nUse weighted selection by source file? [y/N]: "
    ).strip().lower()
    if use_weights.startswith("y"):
        print(
            "Enter a *relative* weight for each file. "
            "Higher numbers mean that file's boards are used more often.\n"
            "For example, weights 1,2,1 make the second file appear about twice "
            "as often as each of the others. Weights do NOT need to sum to 100; "
            "a weight of 0 means 'never use this file'."
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

    # 6) Ask for output filename (stem; we always write .lin)
    default_stem = "combined"
    out_stem = input(
        "\nUser can determine combined LIN file name "
        f"[{default_stem}]: "
    ).strip() or default_stem

    if not out_stem.lower().endswith(".lin"):
        out_name = out_stem + ".lin"
    else:
        out_name = out_stem

    output_path = base_dir / out_name

    # 7) Optional seed
    seed_str = input(
        "Random seed for shuffling (integer 1 to 2 billion or blank for default): "
    ).strip()
    seed = None
    if seed_str:
        try:
            seed = int(seed_str)
        except ValueError:
            print("Seed must be an integer; ignoring and proceeding with default random behaviour.")
            seed = None
    # 8) Combine
    try:
        combine_lin_files(
            input_paths=chosen_files,
            output_path=output_path,
            seed=seed,
            weights=file_weights,
        )
    except Exception as exc:
        print(f"\nERROR: failed to combine LIN files: {exc}")
        return

    print(f"\nCombined {len(chosen_files)} LIN files into: {output_path}")
    print("Deal numbers have been renumbered starting from 1.")
    