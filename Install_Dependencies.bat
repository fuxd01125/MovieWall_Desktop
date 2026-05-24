@echo off
cd /d "%~dp0"
echo Installing MovieWall desktop dependencies...
python -m pip install -r requirements_desktop.txt
if errorlevel 9009 (
  py -3 -m pip install -r requirements_desktop.txt
)
pause
