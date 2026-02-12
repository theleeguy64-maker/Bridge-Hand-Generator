# bridge_engine/menu_help.py

from __future__ import annotations

from typing import Dict

# Central registry of help text for all menus.
# Add/edit entries here; everything else just calls get_menu_help("some_key").
_MENU_HELP: Dict[str, str] = {
    "main_menu": """\
=== Bridge Hand Generator – Main Menu ===

This is the top-level menu for the whole application.

Options:
  0) Exit
      Quit the program and return to your shell.

  1) Profile management
      Open the Profile Manager. From there you can:
        • List profiles on disk
        • Create new profiles (metadata-only wizard with standard constraints
          pre-attached)
        • View / print full profile details
        • Edit metadata only (name, description, tag, dealer, order, author,
          version, rotate flag, NS role / index settings)
        • Edit constraints only (keep metadata, change seat constraints)
        • Delete profiles
        • Save a profile as a new version
        • Work with draft *_TEST.json profiles via Draft Tools

  2) Deal generation
      Run the main deal generator using a chosen profile. Typical flow:
        • Choose a profile
        • Enter owner / player name (for labelling output)
        • Choose base output directory (TXT and LIN are written under this)
        • Choose number of deals to generate
        • Decide whether to use the default seeded run
        • Decide whether to randomly rotate deals (swap N/S and E/W)
      The generator then:
        • Validates the profile
        • Attempts to build the requested number of deals
        • Writes TXT + LIN files
        • Prints a session summary and optional diagnostics.

  3) Admin
      Open the Admin submenu for tools that aren’t core deal generation, such
      as LIN file combination. Use this when you want to post-process or
      inspect outputs, rather than generate new deals from a profile.

  4) Help
      Show this help text describing the main menu and where to go next.

Tips:
  • If you’re unsure where to start, go to "1) Profile management" and
    inspect an existing profile before generating deals.
  • You can always return here from submenus and choose "0) Exit" to quit.
""",

    "admin_menu": """\
=== Bridge Hand Generator – Admin Menu ===

This menu contains tools and utilities that are not part of the core
deal generation flow.

Options:
  0) Exit
      Return to the main menu.

  1) LIN Combiner
      Combine multiple LIN files into a single output file.
      Typical flow:
        • Select one or more source LIN files.
        • Optionally assign integer weights (e.g. 2,1,1) to control how often
          deals from each file appear in the combined output.
        • Choose an output path for the combined LIN file.
      Behaviour notes:
        • Boards in the combined file are re-numbered sequentially (1..N).
        • Weights are relative frequencies; if left blank, each file is treated
          as weight 1.

  3) Profile Diagnostic
      Run the v2 deal builder on a chosen profile and print detailed
      failure attribution diagnostics. Useful for analysing which seats
      fail most often and why (shape vs HCP).
      Typical flow:
        - Choose a profile from disk
        - Enter number of boards to diagnose (default 20)
        - View per-board results: shape, HCP, attempt count
        - View aggregate failure attribution table (5 categories x 4 seats)
        - View attempt statistics (total, mean, min, max, wall time)

  4) Help
      Show this help text describing the Admin menu.
""",

    "profile_manager_menu": """\
=== Profile Manager – Overview ===

The Profile Manager is where you define and maintain Hand Profiles.

0) Exit
   Return to the main menu.

1) List profiles
   Show all profiles found in the profiles/ directory.

2) View / print profile (full details)
   Dump full metadata and constraint details for a single profile.

3) Edit profile
   Edit metadata or constraints of an existing profile.

4) Create new profile
   Run the interactive wizard to create a new profile.

5) Delete profile
   Remove a profile JSON file from disk (with confirmation).

6) Save profile as new version
   Copy an existing profile to a new versioned file and optionally
   tweak metadata.

7) Help
   Show this help text.
""",

    "deal_generation_menu": """\
=== Deal Generation – Overview ===

This flow takes a prepared Hand Profile and generates one or more deals.

Typical steps:
  1) Choose a profile
      Select which Hand Profile to use (NS/EW constraints, metadata, etc.).

  2) Enter owner / player name
      A free-text label written into TXT/LIN output (e.g. your name or the
      group the deals are for).

  3) Choose base output directory
      The generator creates subfolders and files under this directory
      for TXT and LIN output.

  4) Enter number of deals
      How many boards you want to generate (e.g. 4, 12, 24).

  5) Seed / rotation options
      – "Use default seeded run?" controls whether a fixed RNG seed is used
        (reproducible run) or a fresh random seed.
      – "Randomly rotate deals?" controls whether deals are randomly rotated
        (swap N/S and E/W) when written.

  6) Generation + output
      The engine:
        – Validates the profile
        – Attempts to build each board respecting constraints
        – Writes TXT and LIN outputs
        – Prints a summary, and, if enabled, run diagnostics (per-seat success
          rates, RS usage, etc.).

If generation is interrupted (Ctrl-C), partial diagnostics may still be printed
to help you diagnose constraint tightness or RS behaviour.
""",

    "exclusions": """\
=== Sub-profile Exclusions -- Help ===

Exclusions let you reject specific hand shapes AFTER a hand has passed
the standard constraints for a seat's sub-profile. If a dealt hand
matches an exclusion, the generator discards it and retries.

There are two types of exclusion:

1) SHAPES -- Exclude exact 4-digit suit-length patterns
   Each shape is 4 digits representing Spades-Hearts-Diamonds-Clubs
   and must sum to 13.

   Examples:
     4333  = exactly 4 spades, 3 hearts, 3 diamonds, 3 clubs
     4432  = exactly 4 spades, 4 hearts, 3 diamonds, 2 clubs
     5332  = exactly 5 spades, 3 hearts, 3 diamonds, 2 clubs

   Enter shapes as comma-separated values (e.g. 4333,4432).
   A hand matching ANY of the listed shapes is excluded.

2) RULES -- Exclude by suit-group clause (up to 2 clauses, AND logic)
   Each clause has three parts:
     group     = which suits to check:
                   ANY   = all 4 suits (S, H, D, C)
                   MAJOR = majors only (S, H)
                   MINOR = minors only (D, C)
     length_eq = the exact suit length to look for (0-13)
     count     = how many suits in the group must have that length

   Examples:
     MAJOR length_eq=4 count=2
       -> exclude if BOTH majors have exactly 4 cards (4-4 in majors)

     ANY length_eq=3 count=4
       -> exclude if ALL four suits have exactly 3 cards (4333 family)

   With two clauses (AND):
     Clause 1: MAJOR length_eq=4 count=2
     Clause 2: MINOR length_eq=3 count=1
       -> exclude hands with 4-4 majors AND exactly one 3-card minor

Tips:
  - Shapes are simpler but only match exact patterns.
  - Rules are more flexible for families of shapes.
  - Each exclusion targets one sub-profile index on one seat.
  - You can add multiple exclusions per seat.
""",
}


def get_menu_help(key: str) -> str:
    """
    Return help text for the given menu key.

    If the key is unknown, return a generic placeholder so calling code
    never crashes just because help text is missing.
    """
    return _MENU_HELP.get(
        key,
        "No further help is available for this menu yet.",
    )