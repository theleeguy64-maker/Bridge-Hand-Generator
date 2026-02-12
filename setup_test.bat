@echo off
REM ============================================================
REM Bridge Hand Generator — Setup Test (Windows)
REM
REM Test-only version: checks Python + creates venv, no smoke test.
REM
REM What this does:
REM   0. Asks where to install (default: your home folder)
REM   1. Creates folder structure at the chosen location
REM   2. Copies app files from this folder to the install location
REM   3. Checks for Python 3.11+ (guides you to install if needed)
REM   4. Creates a virtual environment (.venv)
REM
REM All output is logged to setup_log.txt in the install folder.
REM If something goes wrong, send that file to the developer.
REM ============================================================

setlocal enabledelayedexpansion

REM -- Resolve the directory this script lives in (the zip/extract location) --
set "SOURCE_DIR=%~dp0"
cd /d "%SOURCE_DIR%"

echo.
echo === Bridge Hand Generator — Setup Test ===
echo.

REM ================================================================
REM Step 0: Choose install location
REM ================================================================
set "DEFAULT_DIR=%USERPROFILE%\BridgeHandGenerator"

echo Where do you want to install BridgeHandGenerator?
echo.
echo   Default: %DEFAULT_DIR%
echo.
set "INSTALL_DIR="
set /p "INSTALL_DIR=Press ENTER to accept, or type a different path: "

REM If user just pressed Enter, use the default
if not defined INSTALL_DIR set "INSTALL_DIR=%DEFAULT_DIR%"

REM Remove any trailing backslash
if "!INSTALL_DIR:~-1!"=="\" set "INSTALL_DIR=!INSTALL_DIR:~0,-1!"

echo.
echo [Step 0] Install location: !INSTALL_DIR!

REM -- Check if we're already running from the install location --
REM    (Compare SOURCE_DIR without trailing backslash to INSTALL_DIR)
set "SOURCE_COMPARE=%SOURCE_DIR%"
if "!SOURCE_COMPARE:~-1!"=="\" set "SOURCE_COMPARE=!SOURCE_COMPARE:~0,-1!"
set "SKIP_COPY=0"
if /i "!SOURCE_COMPARE!"=="!INSTALL_DIR!" set "SKIP_COPY=1"

REM -- Start logging (in the install location) --
REM    Create install dir first so we can write the log there
if not exist "!INSTALL_DIR!" (
    mkdir "!INSTALL_DIR!" 2>nul
    if !errorlevel! neq 0 (
        echo.
        echo [Step 0] FAILED -- cannot create folder: !INSTALL_DIR!
        echo Check the path is valid and you have permission.
        echo.
        pause
        exit /b 1
    )
)

set "LOG_FILE=!INSTALL_DIR!\setup_log.txt"
echo. > "!LOG_FILE!"
echo === Bridge Hand Generator — Setup Test === >> "!LOG_FILE!"
echo. >> "!LOG_FILE!"
echo Date    : %date% %time% >> "!LOG_FILE!"
for /f "tokens=*" %%i in ('ver') do echo OS      : %%i >> "!LOG_FILE!"
echo Source  : %SOURCE_DIR% >> "!LOG_FILE!"
echo Install : !INSTALL_DIR! >> "!LOG_FILE!"
echo. >> "!LOG_FILE!"

echo Date    : %date% %time%
for /f "tokens=*" %%i in ('ver') do echo OS      : %%i
echo Source  : %SOURCE_DIR%
echo Install : !INSTALL_DIR!
echo.

echo [Step 0] Install location: !INSTALL_DIR! >> "!LOG_FILE!"

REM -- Check if install folder already has content --
if exist "!INSTALL_DIR!\run.bat" (
    echo [Step 0] Folder already contains BridgeHandGenerator files.
    echo [Step 0] Folder already exists with content >> "!LOG_FILE!"
    echo.
    set "OVERWRITE="
    set /p "OVERWRITE=Overwrite existing files? (Y/N): "
    if /i not "!OVERWRITE!"=="Y" (
        echo.
        echo Setup cancelled.
        echo [Step 0] User cancelled -- folder exists >> "!LOG_FILE!"
        echo [Done] >> "!LOG_FILE!"
        pause
        exit /b 0
    )
    echo [Step 0] User chose to overwrite >> "!LOG_FILE!"
)

REM ================================================================
REM Step 1: Create folder structure
REM ================================================================
echo [Step 1] Creating folder structure...
echo [Step 1] Creating folder structure... >> "!LOG_FILE!"

for %%D in (bridge_engine profiles out) do (
    if not exist "!INSTALL_DIR!\%%D" (
        mkdir "!INSTALL_DIR!\%%D" 2>nul
    )
)

REM Verify folders were created
set "FOLDERS_OK=1"
for %%D in (bridge_engine profiles out) do (
    if not exist "!INSTALL_DIR!\%%D" set "FOLDERS_OK=0"
)

if "!FOLDERS_OK!"=="0" (
    echo [Step 1] FAILED -- could not create subfolders.
    echo [Step 1] FAILED -- subfolder creation error >> "!LOG_FILE!"
    echo [Done] >> "!LOG_FILE!"
    pause
    exit /b 1
)

echo [Step 1] Folders created: bridge_engine, profiles, out
echo [Step 1] Folders created: bridge_engine, profiles, out >> "!LOG_FILE!"

REM ================================================================
REM Step 2: Copy files to install location
REM ================================================================
if "!SKIP_COPY!"=="1" (
    echo [Step 2] Already running from install location -- skipping copy.
    echo [Step 2] Skipped -- already at install location >> "!LOG_FILE!"
) else (
    echo [Step 2] Copying files to install location...
    echo [Step 2] Copying files to install location... >> "!LOG_FILE!"

    REM Copy app files (bridge_engine and profiles with contents if present)
    if exist "%SOURCE_DIR%bridge_engine\*" (
        xcopy /E /I /Y "%SOURCE_DIR%bridge_engine" "!INSTALL_DIR!\bridge_engine" >nul 2>&1
    )
    if exist "%SOURCE_DIR%profiles\*" (
        xcopy /E /I /Y "%SOURCE_DIR%profiles" "!INSTALL_DIR!\profiles" >nul 2>&1
    )

    REM Copy individual files
    if exist "%SOURCE_DIR%run.bat" copy /Y "%SOURCE_DIR%run.bat" "!INSTALL_DIR!\" >nul 2>&1
    if exist "%SOURCE_DIR%README_WIN.txt" copy /Y "%SOURCE_DIR%README_WIN.txt" "!INSTALL_DIR!\" >nul 2>&1

    echo [Step 2] Files copied.
    echo [Step 2] Files copied >> "!LOG_FILE!"
)

echo.

REM -- Switch to install directory for remaining steps --
cd /d "!INSTALL_DIR!"

REM ================================================================
REM Step 3: Check for Python 3.11+
REM ================================================================
echo [Step 3] Checking for Python 3.11+...
echo [Step 3] Checking for Python 3.11+... >> "!LOG_FILE!"

set "PYTHON_CMD="

REM Try 'py' launcher first (installed by python.org installer)
where py >nul 2>&1
if %errorlevel% equ 0 (
    for /f "tokens=*" %%v in ('py -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2^>nul') do set "PY_VER=%%v"
    if defined PY_VER (
        for /f "tokens=1,2 delims=." %%a in ("!PY_VER!") do (
            if %%a geq 3 if %%b geq 11 (
                set "PYTHON_CMD=py"
            )
        )
    )
)

REM Try 'python' if py didn't work
if not defined PYTHON_CMD (
    where python >nul 2>&1
    if %errorlevel% equ 0 (
        for /f "tokens=*" %%v in ('python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2^>nul') do set "PY_VER=%%v"
        if defined PY_VER (
            for /f "tokens=1,2 delims=." %%a in ("!PY_VER!") do (
                if %%a geq 3 if %%b geq 11 (
                    set "PYTHON_CMD=python"
                )
            )
        )
    )
)

REM Try 'python3' as last resort
if not defined PYTHON_CMD (
    where python3 >nul 2>&1
    if %errorlevel% equ 0 (
        for /f "tokens=*" %%v in ('python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2^>nul') do set "PY_VER=%%v"
        if defined PY_VER (
            for /f "tokens=1,2 delims=." %%a in ("!PY_VER!") do (
                if %%a geq 3 if %%b geq 11 (
                    set "PYTHON_CMD=python3"
                )
            )
        )
    )
)

REM -- If Python found, skip the install prompt --
if defined PYTHON_CMD (
    echo [Step 3] Found Python !PY_VER! via !PYTHON_CMD! command
    echo [Step 3] Found Python !PY_VER! via !PYTHON_CMD! command >> "!LOG_FILE!"
    goto :python_found
)

REM -- Python not found: guide user to install --
echo [Step 3] Python 3.11+ not found on this PC.
echo [Step 3] Python 3.11+ NOT FOUND >> "!LOG_FILE!"
echo.
echo ============================================
echo   Please install Python from python.org
echo ============================================
echo.
echo A download page will open in your browser.
echo Install Python using the Windows installer.
echo.
echo IMPORTANT: Tick the box "Add Python to PATH"
echo            on the first installer screen!
echo.

REM Open the python.org downloads page in the default browser
start https://www.python.org/downloads/

echo After the install finishes, come back here and press any key.
echo.

:retry_python
pause
echo.
echo [Step 3] Re-checking for Python...
echo [Step 3] Re-checking for Python... >> "!LOG_FILE!"

set "PYTHON_CMD="
where py >nul 2>&1
if %errorlevel% equ 0 (
    for /f "tokens=*" %%v in ('py -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2^>nul') do set "PY_VER=%%v"
    if defined PY_VER (
        for /f "tokens=1,2 delims=." %%a in ("!PY_VER!") do (
            if %%a geq 3 if %%b geq 11 (
                set "PYTHON_CMD=py"
            )
        )
    )
)

if not defined PYTHON_CMD (
    where python >nul 2>&1
    if %errorlevel% equ 0 (
        for /f "tokens=*" %%v in ('python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2^>nul') do set "PY_VER=%%v"
        if defined PY_VER (
            for /f "tokens=1,2 delims=." %%a in ("!PY_VER!") do (
                if %%a geq 3 if %%b geq 11 (
                    set "PYTHON_CMD=python"
                )
            )
        )
    )
)

if defined PYTHON_CMD (
    echo [Step 3] Found Python !PY_VER! via !PYTHON_CMD! command
    echo [Step 3] Found Python !PY_VER! via !PYTHON_CMD! command >> "!LOG_FILE!"
    goto :python_found
)

echo.
echo [Step 3] Still not found. Make sure the Python installer completed
echo          and that you ticked "Add Python to PATH".
echo.
echo You may need to close this window and double-click setup again.
echo.
echo [Step 3] Still not found after retry >> "!LOG_FILE!"
goto retry_python

:python_found
echo.

REM ================================================================
REM Step 4: Create virtual environment
REM ================================================================
echo [Step 4] Creating virtual environment...
echo [Step 4] Creating virtual environment... >> "!LOG_FILE!"

if exist ".venv\Scripts\python.exe" (
    echo [Step 4] Virtual environment already exists -- skipping creation.
    echo [Step 4] Virtual environment already exists -- skipped >> "!LOG_FILE!"
) else (
    %PYTHON_CMD% -m venv .venv
    if %errorlevel% neq 0 (
        echo [Step 4] FAILED -- could not create virtual environment.
        echo [Step 4] FAILED -- venv creation error >> "!LOG_FILE!"
        echo.
        echo === Setup FAILED ===
        echo.
        echo Please send this file to the developer:
        echo   !LOG_FILE!
        echo.
        echo [Done] >> "!LOG_FILE!"
        pause
        exit /b 1
    )
    echo [Step 4] Virtual environment created.
    echo [Step 4] Virtual environment created >> "!LOG_FILE!"
)

echo.
echo === Setup complete! ===
echo.
echo BridgeHandGenerator is installed at:
echo   !INSTALL_DIR!
echo.
echo To run the app, double-click run.bat in that folder.
echo.
if not "!SKIP_COPY!"=="1" (
    echo You can delete the setup folder you unzipped.
    echo.
)
echo Setup complete >> "!LOG_FILE!"
echo [Done] >> "!LOG_FILE!"

pause
