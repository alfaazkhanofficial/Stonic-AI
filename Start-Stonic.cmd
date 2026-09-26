@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe goto missing
if not exist node_modules\electron\dist\electron.exe goto missing
call npm.cmd start
if errorlevel 1 pause
exit /b
:missing
echo Please run Setup-Stonic.cmd first.
pause
