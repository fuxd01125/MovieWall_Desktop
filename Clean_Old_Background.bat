@echo off
cd /d "%~dp0"
echo Cleaning old MovieWall background processes...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ports = Get-NetTCPConnection -LocalPort 5000 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique; foreach ($p in $ports) { Stop-Process -Id $p -Force -ErrorAction SilentlyContinue }; $procs = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'MovieWall|app.py|desktop_app.py|pythonw.exe' }; foreach ($p in $procs) { Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue }"
echo Done.
pause
