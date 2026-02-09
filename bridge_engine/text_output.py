
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Sequence, List

RANK_ORDER = "AKQJT98765432"
SUIT_SYMBOLS = {"S": "♠", "H": "♥", "D": "♦", "C": "♣"}

@dataclass(frozen=True)
class FormattedDeal:
    board_number: int
    hands: Dict[str, Sequence[str]]
    dealer: str
    vulnerability: str

def format_deal_text(deal: FormattedDeal) -> str:
    header = f"Board {deal.board_number} — Dealer: {_name(deal.dealer)} — Vul: {deal.vulnerability}"
    north = _format_hand(deal.hands["N"])
    south = _format_hand(deal.hands["S"])
    west = _format_hand(deal.hands["W"])
    east = _format_hand(deal.hands["E"])
    return (
        f"{header}\n\n"
        f"{_center('North')}\n{_indent(north)}\n\n"
        f"{_side_by_side(west, east)}\n\n"
        f"{_center('South')}\n{_indent(south)}"
    ).rstrip()

def print_deal_to_console(deal: FormattedDeal) -> None:
    print(format_deal_text(deal))

def format_multiple_deals_text(deals):
    return "\n\n".join(format_deal_text(d) for d in deals)

def print_multiple_deals_to_console(deals):
    print(format_multiple_deals_text(deals))

def write_multiple_deals_to_text_file(path: Path, deals):
    path.write_text(format_multiple_deals_text(deals), encoding="utf-8")

def _format_hand(cards):
    suits = {"S": [], "H": [], "D": [], "C": []}
    for c in cards:
        suits[c[1]].append(c[0])
    for s in suits:
        suits[s].sort(key=lambda r: RANK_ORDER.index(r))
    return "\n".join(f"{SUIT_SYMBOLS[s]} {' '.join(suits[s])}".rstrip() for s in ["S","H","D","C"])

def _name(seat):
    return {"N":"North","S":"South","E":"East","W":"West"}[seat]

def _center(t, w=25):
    return t.center(w)

def _indent(block, spaces=11):
    p=" "*spaces
    return "\n".join(p+line for line in block.splitlines())

def _side_by_side(west, east):
    wl=west.splitlines(); el=east.splitlines()
    rows=["West".ljust(20) + "East".rjust(20)]
    for i in range(max(len(wl),len(el))):
        L = wl[i] if i<len(wl) else ""
        R = el[i] if i<len(el) else ""
        rows.append(f"{L:<20}    {R}")
    return "\n".join(rows)
