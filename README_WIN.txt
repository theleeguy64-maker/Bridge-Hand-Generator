Bridge Hand Generator - Quick Start (Windows)
===============================================

FIRST TIME SETUP (one-time only)
---------------------------------
1. Unzip BridgeHandGenerator.zip to a folder on your PC
   (e.g. Desktop or Documents)
2. Double-click "setup.bat"
   - Windows may show "Windows protected your PC" -> Click
     "More info" then "Run anyway"
   - If Python is not installed, a download page will open
   - Install Python using the installer
     IMPORTANT: Tick "Add Python to PATH" on the first screen!
   - After installing Python, come back to the setup window
     and press any key
   - When you see "Setup complete!" you're ready to go

RUNNING THE APP
----------------
1. Double-click "run.bat"
2. The Bridge Hand Generator main menu will appear

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
- "Windows protected your PC" when running .bat files:
  Click "More info" then "Run anyway".
  You only need to do this once per file.

- "Virtual environment not found" when running:
  Run setup.bat first.

- Python not found after installing:
  Make sure you ticked "Add Python to PATH" during install.
  You may need to close the setup window and double-click
  setup.bat again.

- Setup failed or app crashes:
  Find "setup_log.txt" in the same folder as setup.bat.
  Send that file to the developer.

FILES
------
  setup.bat         One-time setup script
  run.bat           App launcher (double-click to start)
  bridge_engine\    Application code
  profiles\         Constraint profile JSON files
  README.txt        This file
