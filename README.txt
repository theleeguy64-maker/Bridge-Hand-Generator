Bridge Hand Generator - Quick Start
====================================

FIRST TIME SETUP (one-time only)
---------------------------------
1. Unzip BridgeHandGenerator.zip to a folder on your Mac
2. Double-click "setup.command"
   - macOS may ask "Are you sure you want to open this?"  -> Click Open
   - This installs Python (if needed) and prepares the app
   - Takes about 2 minutes on first run
3. When you see "Setup complete!" you're ready to go

RUNNING THE APP
----------------
1. Double-click "run.command"
   - macOS may ask "Are you sure you want to open this?"  -> Click Open
   - The Bridge Hand Generator main menu will appear

MAIN MENU
----------
  0) Exit
  1) Profile management  — view, edit, create constraint profiles
  2) Deal generation     — generate bridge deals from a profile
  3) Admin               — diagnostics, LIN tools, draft management
  4) Help

PROFILES
---------
Profiles define what kind of bridge hands to generate. Each profile
specifies constraints for all four seats (N, E, S, W):
  - HCP ranges (e.g. 12-14 points)
  - Suit lengths (e.g. 5+ spades)
  - Special constraints (random suit, partner contingent, etc.)

Pre-built profiles are included in the "profiles" folder.
You can create new ones via Profile Management (option 1).

TROUBLESHOOTING
----------------
- "Virtual environment not found" when running:
  Run setup.command first.

- "Python not found" during setup:
  The setup script will install Python automatically via Homebrew.
  You need an internet connection for first-time setup.

- macOS blocks the file ("unidentified developer"):
  Right-click the .command file -> Open -> Click Open.
  You only need to do this once per file.

- App crashes or shows an error:
  Note the error message and contact the developer.

FILES
------
  setup.command     One-time setup script
  run.command       App launcher (double-click to start)
  bridge_engine/    Application code
  profiles/         Constraint profile JSON files
  README.txt        This file
