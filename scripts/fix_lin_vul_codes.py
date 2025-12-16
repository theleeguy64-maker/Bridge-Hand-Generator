#!/usr/bin/env python3
"""
Fix vulnerability codes in your four LIN files.

Replaces:
    |sv|x|   (invalid / old-style)
with:
    |sv|0|   (correct BBO "no vulnerability")

Creates a .bak backup of each file before modifying it.
"""

from pathlib import Path

FILES = [
    "Lee_Responding with a Major to 1NT Opening_BBO_1130_0844.lin",
    "Lee_Our 1 Major & Opponents Interrference_BBO_1130_0844.lin",
    "Lee_Ops interference over our 1NT_BBO_1130_0844.lin",
    "Lee_Defense to 3 Weak 2s_BBO_1130_0844.lin",
]

def fix_file(path: Path):
    if not path.exists():
        print(f"[SKIP] {path.name} not found.")
        return
    
    text = path.read_text(encoding="utf-8")
    if "|sv|x|" not in text:
        print(f"[OK]   {path.name}: no 'x' vulnerability codes found.")
        return
    
    # Backup
    backup = path.with_suffix(path.suffix + ".bak")
    backup.write_text(text, encoding="utf-8")
    
    # Replace
    fixed = text.replace("|sv|x|", "|sv|0|")
    path.write_text(fixed, encoding="utf-8")
    
    print(f"[FIX]  {path.name}: replaced all '|sv|x|' with '|sv|0|'")
    print(f"       Backup saved as {backup.name}")


def main():
    root = Path(".")  # current directory
    print("=== Fixing LIN vulnerability codes ===\n")
    
    for fname in FILES:
        fix_file(root / fname)

    print("\n=== Done ===")


if __name__ == "__main__":
    main()