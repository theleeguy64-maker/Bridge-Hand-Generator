# file: bridge_engine/cli_io.py
from __future__ import annotations

import sys
from typing import Optional, Sequence, TypeVar

T = TypeVar("T")


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


def _input_choice(
    prompt: str,
    choices: Sequence[str],
    default: Optional[str] = None,
) -> str:
    """
    Prompt the user to choose one of `choices`.

    Comparison is case-insensitive; the returned value is the original
    entry from `choices`.
    """
    if not choices:
        raise ValueError("_input_choice requires a non-empty choices sequence.")

    canonical = {str(c).upper(): c for c in choices}
    choice_str = "/".join(str(c) for c in choices)

    while True:
        if default is not None:
            full_prompt = f"{prompt} ({choice_str}) [default {default}]: "
        else:
            full_prompt = f"{prompt} ({choice_str}): "

        try:
            raw = input(full_prompt).strip()
        except EOFError:
            raise RuntimeError("Input aborted (EOF) while prompting user.")

        if not raw and default is not None:
            raw = default

        key = raw.upper()
        if key in canonical:
            return canonical[key]

        print(f"Please type one of: {choice_str}", file=sys.stderr)


def clear_screen() -> None:
    """Clear terminal screen — safe no-op fallback."""
    try:
        import os
        os.system("cls" if os.name == "nt" else "clear")
    except Exception:
        # In tests or non-interactive envs, just ignore
        pass


from typing import Optional


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


def safe_input_int_with_default(
    prompt: str,
    *,
    minimum: int,
    maximum: int,
    default: int,
    suffix: str = "",
) -> int:
    """
    Like prompt_int_in_range, but with a default and safer blank handling.

    Used by the profile wizard tests. Signature is keyword-only so calls like

        safe_input_int_with_default(
            "Min cards",
            minimum=0,
            maximum=13,
            default=0,
            suffix="(0–13)"
        )

    work as expected.
    """
    while True:
        range_part = f" ({minimum}-{maximum})"
        suffix_part = f" {suffix}" if suffix else ""
        default_part = f" [{default}]"
        full_prompt = f"{prompt}{range_part}{suffix_part}{default_part}: "

        raw = input(full_prompt).strip()
        if raw == "":
            return default

        try:
            value = int(raw)
        except ValueError:
            print("Please enter a whole number.")
            continue

        if value < minimum or value > maximum:
            print(f"Please enter a value between {minimum} and {maximum}.")
            continue

        return value