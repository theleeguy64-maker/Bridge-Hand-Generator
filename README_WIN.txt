Bridge Hand Generator - Quick Start (Windows)
===============================================

FIRST TIME SETUP (one-time only)
---------------------------------
1. Right-click the .zip file and choose "Extract All..."
   Extract it anywhere (e.g. Desktop). This is just temporary.

2. Open the extracted folder and double-click "setup.bat"
   - Windows may show "Windows protected your PC" -> Click
     "More info" then "Run anyway"

3. Setup will ask where to install BridgeHandGenerator.
   Press ENTER to accept the default location, or type a
   different path.
   Default: C:\Users\<YourName>\BridgeHandGenerator

4. Setup will find or help you install Python 3.11+
   - If Python is not installed, a download page will open
   - Install Python using the installer
     IMPORTANT: Tick "Add Python to PATH" on the first screen!
   - After installing Python, come back to the setup window
     and press any key

5. When you see "Setup complete!" you're done.
   You can delete the extracted setup folder.

RUNNING THE APP
----------------
1. Go to the install folder (e.g. C:\Users\<YourName>\BridgeHandGenerator)
2. Double-click "run.bat"
3. The Bridge Hand Generator main menu will appear

MAIN MENU
----------
  0) Exit
  1) Profile management  -- view, edit, create constraint profiles
  2) Deal generation     -- generate bridge deals from a profile
  3) Admin               -- diagnostics, LIN tools, draft management
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
  Find "setup_log.txt" in the install folder.
  Send that file to the developer.

FILES (after setup)
--------------------
  run.bat           App launcher (double-click to start)
  bridge_engine\    Application code
  profiles\         Constraint profile JSON files
  out\              Generated deals output
  .venv\            Python virtual environment (created by setup)
  setup_log.txt     Setup log (for troubleshooting)
  README_WIN.txt    This file
