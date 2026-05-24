@echo off
cd /d "%~dp0"
echo Running MovieWall desktop debug mode...
python desktop_app.py
if errorlevel 9009 (
  py -3 desktop_app.py
)
pause
