"""I/O wrapper functions for the profile wizard.

These names are monkeypatched by tests via bridge_engine.profile_wizard.
We keep them in a dedicated module and re-export them.
"""

from __future__ import annotations

from typing import Sequence

from . import cli_io


def _input_with_default(prompt: str, default: str) -> str:
    """
    Backwards-compat: tests monkeypatch profile_wizard._input_with_default.
    Delegate to cli_io so CLI UX stays consistent.
    """
    return cli_io._input_with_default(prompt, default)


def _yes_no(prompt: str, default: bool = True) -> bool:
    """
    Backwards-compat: tests monkeypatch profile_wizard._yes_no.
    """
    return cli_io._yes_no(prompt, default=default)


def _yes_no_help(prompt: str, help_key: str, default: bool = True) -> bool:
    """
    Yes/no prompt with inline help support.
    Delegates to cli_io._yes_no_help.
    """
    return cli_io._yes_no_help(prompt, help_key, default=default)


def _prompt_yne(prompt: str, default: str = "y") -> str:
    """Prompt for y/n/e — delegate to cli_io."""
    return cli_io._prompt_yne(prompt, default=default)


def prompt_str(prompt: str, default: str = "") -> str:
    """
    Prompt for a line of text with an optional default.

    - In normal CLI use: read from stdin and return the entered value
      (or the default if the user just presses Enter).
    - Under pytest's capture (where stdin may raise OSError), fall back
      to returning `default` so tests don't crash.
    """
    try:
        raw = input(prompt)
    except OSError:
        # Under pytest capture: stdin is not readable, so just return default.
        return default

    text = raw.strip()
    return text if text else default


def _input_int(
    prompt: str,
    default: int,
    minimum: int,
    maximum: int,
    show_range_suffix: bool = True,
) -> int:
    """
    Backwards-compat: tests monkeypatch profile_wizard._input_int.
    Delegate to cli_io to preserve exact prompt formatting behavior.
    """
    return cli_io._input_int(
        prompt,
        default=default,
        minimum=minimum,
        maximum=maximum,
        show_range_suffix=show_range_suffix,
    )


def _input_choice(prompt: str, options: Sequence[str], default: str) -> str:
    """
    Choose by typing the value (not by number).
    Tests monkeypatch profile_wizard._input_choice via this seam.
    """
    default_val = default if default in options else (options[0] if options else default)

    while True:
        raw = _input_with_default(prompt, str(default_val)).strip()
        if raw == "":
            return default_val
        if raw in options:
            return raw
        print(f"Please enter one of: {', '.join(options)}")


def clear_screen() -> None:
    """
    Clear the terminal screen.

    Local wrapper so existing code can call clear_screen()
    without caring where it lives.
    """
    cli_io.clear_screen()
