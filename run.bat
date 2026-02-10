@echo off
REM ============================================================
REM Bridge Hand Generator — Launcher (Windows)
REM
REM Double-click this file to start the Bridge Hand Generator.
REM (Run setup.bat first if this is your first time.)
REM ============================================================

REM -- Resolve the directory this script lives in --
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

REM -- Use the venv's Python directly (no PATH dependency) --
set "PYTHON=%SCRIPT_DIR%.venv\Scripts\python.exe"

if not exist "%PYTHON%" (
    echo.
    echo ERROR: Virtual environment not found.
    echo Please run setup.bat first.
    echo.
    pause
    exit /b 1
)

REM -- Launch the app --
echo.
echo === Bridge Hand Generator ===
echo.
"%PYTHON%" -m bridge_engine

echo.
echo === Session ended ===
echo.
pause
