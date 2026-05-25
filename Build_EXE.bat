@echo off
chcp 65001 >nul
title MovieWall EXE Builder
cd /d "%~dp0"
echo MovieWall Desktop EXE Builder V15 (OneFile)
echo ========================================
echo.
python build_desktop.py
if %errorlevel% neq 0 (
    echo.
    echo [*] Python not found, trying py launcher...
    py -3 build_desktop.py
)
if %errorlevel% neq 0 (
    echo.
    echo [*] Trying python3...
    python3 build_desktop.py
)
echo.
pause
