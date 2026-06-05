@echo off
start "" "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" --remote-debugging-port=9222 --user-data-dir="%LOCALAPPDATA%\Microsoft\Edge\User Data" "https://platform.xiaomimimo.com/console/plan-manage"
timeout /t 3 /nobreak >nul
start "" wscript.exe "%~dp0launch.vbs"
exit
