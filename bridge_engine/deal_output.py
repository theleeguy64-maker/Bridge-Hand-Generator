"""
Section D – Rendering deals to TXT and LIN.

Responsibilities
----------------
- Take:
    * SetupResult   (from setup_env)
    * HandProfile   (from hand_profile)
    * DealSet       (from deal_generator; contains Section C Deal objects)
- Produce:
    * Human-readable TXT file
    * BBO-style LIN file
    * Optional console output

This module MUST NOT:
- Regenerate or filter deals.
- Recompute setup paths, timestamps, or seeds.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence

from .deal_generator import Deal, DealSet
from .hand_profile import HandProfile
from .lin_encoder import Deal as LinDeal
from .lin_encoder import write_lin_file
from .setup_env import SetupResult


# ---------------------------------------------------------------------------
# Exceptions and summary types
# ---------------------------------------------------------------------------


class OutputError(Exception):
    """Domain error raised when output writing fails."""


@dataclass
class DealOutputSummary:
    """Summary of what render_deals() produced."""

    num_deals: int
    txt_path: Path
    lin_path: Path
    warnings: List[str]


# ---------------------------------------------------------------------------
# Text formatting helpers
# ---------------------------------------------------------------------------

SUIT_ORDER = "SHDC"
SUIT_SYMBOLS = {"S": "♠", "H": "♥", "D": "♦", "C": "♣"}
RANK_ORDER = "AKQJT98765432"

# Column width for the West hand in horizontal West/East pair formatting.
WE_COLUMN_WIDTH = 28


def _group_cards_by_suit(cards: Sequence[str]) -> Dict[str, List[str]]:
    """
    Group cards into suits and sort ranks within each suit.

    cards: list like ["AS", "KH", ...].
    Returns dict suit -> list of ranks (as single characters).
    """
    result: Dict[str, List[str]] = {s: [] for s in SUIT_ORDER}

    for card in cards:
        if len(card) != 2:
            continue
        rank, suit = card[0], card[1]
        if suit not in result:
            continue
        result[suit].append(rank)

    rank_index = {r: i for i, r in enumerate(RANK_ORDER)}
    for suit in SUIT_ORDER:
        result[suit].sort(key=lambda r: rank_index.get(r, 99))

    return result


def _format_rank_list(ranks: Sequence[str]) -> str:
    if not ranks:
        return "-"
    return " ".join(ranks)


def _format_vertical_hand(cards: Sequence[str], indent: int = 8) -> List[str]:
    """
    Format a single hand as four vertically stacked suit lines:

        ♠ A K Q
        ♥ -
        ♦ T 9
        ♣ J

    Returns the lines WITHOUT final newline characters.
    """
    suits = _group_cards_by_suit(cards)
    lines: List[str] = []
    prefix = " " * indent
    for suit in SUIT_ORDER:
        symbol = SUIT_SYMBOLS[suit]
        ranks = _format_rank_list(suits[suit])
        lines.append(f"{prefix}{symbol} {ranks}")
    return lines


def _format_horizontal_pair(west_cards: Sequence[str], east_cards: Sequence[str]) -> List[str]:
    """
    Format West and East horizontally on the same set of lines, e.g.:

    West                        East
    ♠ A K Q                     ♠ J T 9
    ♥ 9 8                       ♥ -
    ♦ -                         ♦ A K
    ♣ T 3                       ♣ Q J 9
    """
    west_suits = _group_cards_by_suit(west_cards)
    east_suits = _group_cards_by_suit(east_cards)

    lines: List[str] = []
    # Header line
    lines.append("West".ljust(WE_COLUMN_WIDTH) + "East")

    for suit in SUIT_ORDER:
        ws = SUIT_SYMBOLS[suit] + " " + _format_rank_list(west_suits[suit])
        es = SUIT_SYMBOLS[suit] + " " + _format_rank_list(east_suits[suit])
        lines.append(ws.ljust(WE_COLUMN_WIDTH) + es)

    return lines


def _format_single_board_text(board: Deal) -> List[str]:
    """
    Format one Deal as the full block of text that appears in the TXT output.
    """
    lines: List[str] = []

    lines.append(f"Board {board.board_number}")
    lines.append(f"Dealer       : {board.dealer}")
    lines.append(f"Vulnerability: {board.vulnerability}")
    lines.append("")  # blank line

    # --- New NS indent behaviour (+6 spaces vs previous) ---
    NS_EXTRA = 6
    NS_HEADER_INDENT = 11 + NS_EXTRA  # was 11 ("           ")
    NS_SUIT_INDENT = 8 + NS_EXTRA  # was 8 (default in _format_vertical_hand)

    # North
    lines.append(" " * NS_HEADER_INDENT + "North")
    lines.extend(_format_vertical_hand(board.hands["N"], indent=NS_SUIT_INDENT))
    lines.append("")

    # West / East pair (unchanged)
    lines.extend(_format_horizontal_pair(board.hands["W"], board.hands["E"]))
    lines.append("")

    # South
    lines.append(" " * NS_HEADER_INDENT + "South")
    lines.extend(_format_vertical_hand(board.hands["S"], indent=NS_SUIT_INDENT))
    lines.append("")

    return lines


def _convert_to_formatted_deals(profile: HandProfile, deals: Sequence[Deal]) -> List[str]:
    """
    Build the full TXT file content as a list of lines, including:

      - One-time header:
          Profile, Tag, Author, Version
          "You and your partner are always North–South."
      - For each deal:
          Board number, dealer, vulnerability
          Compass layout
          Separator line between deals
    """
    lines: List[str] = []

    # One-time profile header
    profile_name = profile.profile_name
    tag = profile.tag
    author = profile.author
    version = profile.version

    lines.append(f"Profile : {profile_name}")
    lines.append(f"Tag     : {tag}")
    lines.append(f"Author  : {author}")
    lines.append(f"Version : {version}")
    lines.append("")
    lines.append("You and your partner are always North–South.")
    lines.append("")
    lines.append("========================================")
    lines.append("")

    # Per-board sections
    first = True
    for d in deals:
        if not first:
            # Visual separator between boards
            lines.append("")
            lines.append("========================================")
            lines.append("")
        first = False

        lines.extend(_format_single_board_text(d))

    return lines


def _write_text_output(
    path: Path,
    formatted_deals: Sequence[str],
    *,
    append: bool,
    print_to_console: bool,
) -> None:
    """
    Write the TXT output file and optionally mirror to stdout.
    """
    text = "\n".join(formatted_deals) + ("\n" if formatted_deals else "")

    if print_to_console:
        print(text)

    try:
        if append and path.exists():
            existing = path.read_text(encoding="utf-8")
            path.write_text(existing + text, encoding="utf-8")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
    except OSError as exc:
        raise OutputError(f"Failed to write text output to {path}: {exc}") from exc


# ---------------------------------------------------------------------------
# LIN conversion
# ---------------------------------------------------------------------------


def _convert_to_lin_deals(deals: Sequence[Deal]) -> List[LinDeal]:
    """
    Map internal Section C Deal objects into lin_encoder.Deal structures
    ready for LIN encoding.

    We pass board_number, dealer, hands, AND vulnerability so BBO can show
    the correct 'sv' tag.
    """
    lin_deals: List[LinDeal] = []
    for d in deals:
        lin_deals.append(
            LinDeal(
                board_number=d.board_number,
                dealer=d.dealer,
                hands=d.hands,
                vulnerability=d.vulnerability,
            )
        )
    return lin_deals


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def render_deals(
    setup: SetupResult,
    profile: HandProfile,
    deal_set: DealSet,
    *,
    print_to_console: bool = True,
    append_txt: bool = False,
) -> DealOutputSummary:
    """
    Render all deals to text and LIN outputs.

    This function is a thin coordination layer for Section D:
      • Converts internal Deal objects into text and LIN representations.
      • Writes to the canonical paths from SetupResult.
      • Optionally prints deals to the console.

    It MUST NOT:
      • Filter, modify, or regenerate deals.
      • Recompute paths, timestamps, or seeds.
    """
    warnings: List[str] = []

    try:
        # TXT representation
        formatted = _convert_to_formatted_deals(profile, deal_set.deals)

        # LIN representation (now with correct dealer + vulnerability)
        lin_deals = _convert_to_lin_deals(deal_set.deals)

        # Write text file
        _write_text_output(
            setup.output_txt_file,
            formatted_deals=formatted,
            append=append_txt,
            print_to_console=print_to_console,
        )

        # Always overwrite LIN file for a run
        try:
            setup.output_lin_file.parent.mkdir(parents=True, exist_ok=True)
            write_lin_file(setup.output_lin_file, lin_deals)
        except OSError as exc:
            raise OutputError(f"Failed to write LIN output to {setup.output_lin_file}: {exc}") from exc

        return DealOutputSummary(
            num_deals=len(deal_set.deals),
            txt_path=setup.output_txt_file,
            lin_path=setup.output_lin_file,
            warnings=warnings,
        )
    except OutputError:
        # Already wrapped; just re-raise
        raise
    except Exception as exc:
        # Narrow, local wrapping into domain error
        raise OutputError(f"Failed while rendering deals: {exc}") from exc
