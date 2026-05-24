@echo off
cd /d "%~dp0"
echo MovieWall Desktop EXE Builder V12
echo.
python build_desktop.py
if errorlevel 9009 (
  echo Python command not found, trying py launcher...
  py -3 build_desktop.py
)
echo.
pause
