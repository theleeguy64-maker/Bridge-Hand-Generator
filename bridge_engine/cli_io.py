# file: bridge_engine/cli_io.py
from __future__ import annotations

import sys
from typing import Optional


def _input_with_default(prompt: str, default: Optional[str] = None) -> str:
    """
    Prompt the user for a value, showing an optional default.

    Returns the entered string, or the default if the user presses Enter.
    """
    if default is not None:
        full_prompt = f"{prompt} [{default}]: "
    else:
        full_prompt = f"{prompt}: "

    try:
        value = input(full_prompt).strip()
    except EOFError:
        raise RuntimeError("Input aborted (EOF) while prompting user.")

    if not value and default is not None:
        return default
    return value


def clear_screen() -> None:
    """Clear terminal screen — safe no-op fallback."""
    try:
        import os
        import subprocess

        cmd = "cls" if os.name == "nt" else "clear"
        subprocess.run([cmd], check=False)  # noqa: S603
    except Exception:
        # In tests or non-interactive envs, just ignore
        pass


def _input_int(
    prompt: str,
    *,
    default: Optional[int] = None,
    minimum: int,
    maximum: int,
    show_range_suffix: bool = True,
) -> int:
    """
    Prompt the user for an integer within [minimum, maximum].

    If show_range_suffix=True (default), append the suffix:
        (>=minimum and <=maximum)
    to match test expectations exactly.
    """
    # Build range suffix exactly as tests expect
    if show_range_suffix:
        # NOTE: no spaces after >= and <=, per test expectation
        range_suffix = f" (>={minimum} and <={maximum})"
    else:
        range_suffix = ""

    while True:
        if default is not None:
            full_prompt = f"{prompt} [{default}]{range_suffix}: "
        else:
            full_prompt = f"{prompt}{range_suffix}: "

        raw = input(full_prompt).strip()

        if not raw:
            if default is not None:
                return default
            print("Please enter a whole number.")
            continue

        try:
            value = int(raw)
        except ValueError:
            print("Please enter a whole number.")
            continue

        if value < minimum or value > maximum:
            print(f"Please enter a value between {minimum} and {maximum}.")
            continue

        return value


def _yes_no(prompt: str, default: bool = True) -> bool:
    """
    Prompt for a yes/no response.

    Returns True for yes, False for no.
    """
    default_str = "Y/n" if default else "y/N"

    while True:
        try:
            raw = input(f"{prompt} ({default_str}): ").strip().lower()
        except EOFError:
            raise RuntimeError("Input aborted (EOF) while prompting user.")

        if not raw:
            return default
        if raw in {"y", "yes"}:
            return True
        if raw in {"n", "no"}:
            return False

        print("Please answer y or n.", file=sys.stderr)


def _yes_no_help(prompt: str, help_key: str, default: bool = True) -> bool:
    """
    Prompt for a yes/no response with inline help support.

    Accepts "help", "h", or "?" to print context-sensitive help text
    (looked up from menu_help.py via help_key) and re-prompt.

    Returns True for yes, False for no.
    """
    from .menu_help import get_menu_help  # local import avoids circular deps

    default_str = "Y/n/help" if default else "y/N/help"

    while True:
        try:
            raw = input(f"{prompt} ({default_str}): ").strip().lower()
        except EOFError:
            raise RuntimeError("Input aborted (EOF) while prompting user.")

        if not raw:
            return default
        if raw in {"y", "yes"}:
            return True
        if raw in {"n", "no"}:
            return False
        if raw in {"help", "h", "?"}:
            print(get_menu_help(help_key))
            continue

        print("Please answer y, n, or help.", file=sys.stderr)
