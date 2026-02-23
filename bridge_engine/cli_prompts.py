# bridge_engine/cli_prompts.py
from __future__ import annotations

from . import cli_io


def prompt_yes_no(prompt: str, default: bool = True) -> bool:
    """
    Prompt the user for a yes/no answer.

    - Accepts: y, yes, n, no (case-insensitive)
    - Empty input returns `default`
    - Re-prompts on invalid input
    """

    if default:
        suffix = " (Y/n): "
    else:
        suffix = " (y/N): "

    while True:
        raw = input(f"{prompt}{suffix}").strip().lower()

        if raw == "":
            return default
        if raw in ("y", "yes"):
            return True
        if raw in ("n", "no"):
            return False

        print("Please enter y or n.")


def prompt_int(
    prompt: str,
    default: int,
    minimum: int,
    maximum: int,
    *,
    show_range_suffix: bool = True,
) -> int:
    """Integer input with range constraints."""
    return cli_io._input_int(
        prompt,
        default=default,
        minimum=minimum,
        maximum=maximum,
        show_range_suffix=show_range_suffix,
    )
