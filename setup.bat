@echo off
REM ============================================================
REM Bridge Hand Generator — One-Time Setup (Windows)
REM
REM What this does:
REM   1. Checks for Python 3.11+ (guides you to install it if needed)
REM   2. Creates a virtual environment (.venv)
REM   3. Runs a smoke test to confirm everything works
REM
REM All output is logged to setup_log.txt. If something goes wrong,
REM send that file to the developer.
REM
REM Run this once after unzipping. After that, use run.bat.
REM ============================================================

setlocal enabledelayedexpansion

REM -- Resolve the directory this script lives in --
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

REM -- Start logging --
set "LOG_FILE=%SCRIPT_DIR%setup_log.txt"
echo. > "%LOG_FILE%"

echo.
echo === Bridge Hand Generator — Setup ===
echo.

REM -- Log system info --
echo Date    : %date% %time% >> "%LOG_FILE%"
for /f "tokens=*" %%i in ('ver') do echo OS      : %%i >> "%LOG_FILE%"
echo Dir     : %SCRIPT_DIR% >> "%LOG_FILE%"
echo. >> "%LOG_FILE%"

echo Date    : %date% %time%
for /f "tokens=*" %%i in ('ver') do echo OS      : %%i
echo Dir     : %SCRIPT_DIR%
echo.

REM -- Step 1: Check for Python 3.11+ --
set "PYTHON_CMD="

REM Try 'py' launcher first (installed by python.org installer)
where py >nul 2>&1
if %errorlevel% equ 0 (
    for /f "tokens=*" %%v in ('py -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2^>nul') do set "PY_VER=%%v"
    if defined PY_VER (
        for /f "tokens=1,2 delims=." %%a in ("!PY_VER!") do (
            if %%a geq 3 if %%b geq 11 (
                set "PYTHON_CMD=py"
                echo Found Python !PY_VER! via py launcher
                echo Found Python !PY_VER! via py launcher >> "%LOG_FILE%"
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
                    echo Found Python !PY_VER! via python command
                    echo Found Python !PY_VER! via python command >> "%LOG_FILE%"
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
                    echo Found Python !PY_VER! via python3 command
                    echo Found Python !PY_VER! via python3 command >> "%LOG_FILE%"
                )
            )
        )
    )
)

if not defined PYTHON_CMD (
    echo Python 3.11+ not found on this PC.
    echo Python 3.11+ not found >> "%LOG_FILE%"
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
    echo Checking for Python again...

    set "PYTHON_CMD="
    where py >nul 2>&1
    if %errorlevel% equ 0 (
        for /f "tokens=*" %%v in ('py -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2^>nul') do set "PY_VER=%%v"
        if defined PY_VER (
            for /f "tokens=1,2 delims=." %%a in ("!PY_VER!") do (
                if %%a geq 3 if %%b geq 11 (
                    set "PYTHON_CMD=py"
                    echo Found Python !PY_VER! via py launcher
                    echo Found Python !PY_VER! via py launcher >> "%LOG_FILE%"
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
                        echo Found Python !PY_VER! via python command
                        echo Found Python !PY_VER! via python command >> "%LOG_FILE%"
                    )
                )
            )
        )
    )

    if not defined PYTHON_CMD (
        echo.
        echo Still not found. Make sure the Python installer completed
        echo and that you ticked "Add Python to PATH".
        echo.
        echo You may need to close this window and double-click setup.bat again.
        echo.
        goto retry_python
    )
)

echo.

REM -- Step 2: Create virtual environment --
if exist ".venv\Scripts\python.exe" (
    echo Virtual environment (.venv) already exists — skipping creation.
    echo Virtual environment already exists >> "%LOG_FILE%"
) else (
    echo Creating virtual environment...
    echo Creating virtual environment... >> "%LOG_FILE%"
    %PYTHON_CMD% -m venv .venv
    if %errorlevel% neq 0 (
        echo.
        echo === Setup FAILED ===
        echo Could not create virtual environment.
        echo venv creation failed >> "%LOG_FILE%"
        echo.
        echo Please send this file to the developer:
        echo   %LOG_FILE%
        echo.
        pause
        exit /b 1
    )
    echo Virtual environment created.
    echo Virtual environment created >> "%LOG_FILE%"
)

echo.

REM -- Step 3: Smoke test --
echo Running smoke test...
set "VENV_PYTHON=%SCRIPT_DIR%.venv\Scripts\python.exe"

"%VENV_PYTHON%" -c "from bridge_engine.orchestrator import main; print('Import OK')"
if %errorlevel% equ 0 (
    echo.
    echo === Setup complete! ===
    echo.
    echo To run the Bridge Hand Generator:
    echo   Double-click run.bat
    echo.
    echo Setup complete >> "%LOG_FILE%"
) else (
    echo.
    echo === Setup FAILED ===
    echo The smoke test did not pass.
    echo Smoke test failed >> "%LOG_FILE%"
    echo.
    echo Please send this file to the developer:
    echo   %LOG_FILE%
    echo.
)

pause
