# bridge_engine/cli_prompts.py
from __future__ import annotations

from typing import Optional, Sequence, TypeVar

from . import cli_io

T = TypeVar("T")


def prompt_choice(
    prompt: str,
    options: Sequence[T],
    *,
    default_index: int = 0,
    show_options: bool = True,
) -> T:
    """
    Choose one item from `options` by number.

    - Shows a numbered list (1..N) by default
    - User enters a number
    - Empty input returns options[default_index]
    - Re-prompts on invalid input
    """
    if not options:
        raise ValueError("prompt_choice: options must not be empty")

    if default_index < 0 or default_index >= len(options):
        raise ValueError("prompt_choice: default_index out of range")

    if show_options:
        for i, opt in enumerate(options, start=1):
            print(f"  {i}) {opt}")

    while True:
        raw = input(f"{prompt} [{default_index + 1}]: ").strip()

        if raw == "":
            return options[default_index]

        try:
            n = int(raw)
        except ValueError:
            print(f"Please enter a number between 1 and {len(options)}.")
            continue

        if 1 <= n <= len(options):
            return options[n - 1]

        print(f"Please enter a number between 1 and {len(options)}.")


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