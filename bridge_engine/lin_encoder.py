"""
LIN encoder utilities (Section D of Bridge Hand Generator).

This module converts internal Deal objects into BBO-style LIN lines.

Key behaviours
--------------
- Hands are encoded into the `md` tag in BBO's fixed seat order:
    South, West, North, East
  regardless of who the dealer is. The dealer is communicated via
  a numeric dealer code prefix.

- Board numbering:
    * deal.board_number (1-based) is used both for:
        - The container prefix:  qx|o<board_number>|
        - The human-readable title: ah|Board <board_number>|

- Vulnerability mapping:
    * Internal labels: "None", "NS", "EW", "Both"
    * BBO LIN codes (sv):
        "0" -> none
        "n" -> NS vulnerable
        "e" -> EW vulnerable
        "b" -> both vulnerable
"""

# file: bridge_engine/lin_encoder.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence


# Suits in BBO / LIN order
_SUITS = "SHDC"

# Ranks high-to-low, for stable ordering
_RANK_ORDER = "AKQJT98765432"


@dataclass
class Deal:
    """
    Minimal LIN deal representation used by Section D and tests.

    Parameters
    ----------
    board_number:
        1-based board number.
    dealer:
        "N", "E", "S", or "W".
    hands:
        Mapping from seat ("N","E","S","W") to list of cards like "AS", "TD".
    vulnerability:
        "None", "NS", "EW", or "Both". Defaults to "None".
    """

    board_number: int
    dealer: str
    hands: Dict[str, List[str]]
    vulnerability: str = "None"

    def __post_init__(self) -> None:
        if self.dealer not in ("N", "E", "S", "W"):
            raise ValueError(f"Invalid dealer: {self.dealer!r}")
        for seat in self.hands.keys():
            if seat not in ("N", "E", "S", "W"):
                raise ValueError(f"Invalid seat in hands mapping: {seat!r}")


def _rank_sort_key(rank: str) -> int:
    """
    Return sort key for a given rank character.

    Unknown ranks are sorted last; we avoid failing hard here since LIN is
    primarily a serialisation format.
    """
    idx = _RANK_ORDER.find(rank)
    return idx if idx != -1 else len(_RANK_ORDER)


def _hand_to_lin_suits(cards: List[str]) -> str:
    """
    Convert a list of cards (e.g. ["AS", "TD"]) to a compact per-suit string.

    We output in canonical BBO order S, H, D, C as:

        "S<spades>H<hearts>D<diamonds>C<clubs>"

    Example (all spades):
        ["AS", "KS"] -> "SAKSHTD C"
    """
    by_suit: Dict[str, List[str]] = {s: [] for s in _SUITS}
    for card in cards:
        if len(card) != 2:
            # Defensive: ignore malformed cards
            continue
        rank, suit = card[0], card[1]
        if suit not in by_suit:
            continue
        by_suit[suit].append(rank)

    parts: List[str] = []
    for suit in _SUITS:
        ranks = by_suit[suit]
        ranks.sort(key=_rank_sort_key)
        parts.append("".join(ranks))

    # S<spades>H<hearts>D<diamonds>C<clubs>
    return f"S{parts[0]}H{parts[1]}D{parts[2]}C{parts[3]}"


def _dealer_to_bbo_code(dealer: str) -> str:
    """
    Map compass dealer seat to BBO 'md' dealer code.

        1 = South, 2 = West, 3 = North, 4 = East
    """
    mapping = {"S": "1", "W": "2", "N": "3", "E": "4"}
    # Default to North (3) if somehow unknown – defensive only.
    return mapping.get(dealer, "3")


def _vul_to_bbo_code(vul: str) -> str:
    """
    Map internal vulnerability labels to BBO LIN 'sv' codes.

    BBO uses single-letter codes:
        '0' -> none
        'n' -> NS vulnerable
        'e' -> EW vulnerable
        'b' -> both vulnerable
    """
    mapping = {
        "None": "0",
        "NS": "n",
        "EW": "e",
        "Both": "b",
    }
    # Default to '0' (none) for unexpected values.
    return mapping.get(vul, "0")


def encode_deal_to_lin_line(deal: Deal) -> str:
    """
    Encode a single deal into a BBO LIN line.

    Structure:

        qx|o<board_number>|
        md|<dealerCode><South-hand>,<West-hand>,<North-hand>,<East-hand>|
        ah|Board <board_number>|
        sv|<vulCode>|
        pg||

    Notes
    -----
    * BBO expects the hand segments in S, W, N, E order, regardless of
      who the dealer is. The dealerCode (1–4) tells BBO who deals.
    """
    dealer_code = _dealer_to_bbo_code(deal.dealer)

    # BBO hand order: South, West, North, East
    south = _hand_to_lin_suits(deal.hands.get("S", []))
    west = _hand_to_lin_suits(deal.hands.get("W", []))
    north = _hand_to_lin_suits(deal.hands.get("N", []))
    east = _hand_to_lin_suits(deal.hands.get("E", []))

    md_part = f"md|{dealer_code}{south},{west},{north},{east}"

    # Board title and container index use board_number directly
    board_title = f"Board {deal.board_number}"
    container = f"qx|o{deal.board_number}|"

    # Vulnerability mapping
    vul_code = _vul_to_bbo_code(deal.vulnerability)

    return f"{container}{md_part}|ah|{board_title}|sv|{vul_code}|pg||"


def write_lin_file(path: Path, deals: Sequence[Deal]) -> None:
    """
    Write one LIN line per deal to the given path.
    """
    lines: List[str] = [encode_deal_to_lin_line(d) for d in deals]
    text = "\n".join(lines) + "\n"
    path.write_text(text, encoding="utf-8")
