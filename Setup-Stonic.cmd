@echo off
cd /d "%~dp0"
where uv >nul 2>&1
if errorlevel 1 (
  echo Install uv and Node.js 22 or later, then run this setup again. See README.md.
  pause
  exit /b 1
)

rem Voice/STT/TTS was retired from STONIC V2. Remove every legacy voice
rem source/runtime artifact when updating an older voice-enabled checkout.
echo Removing retired voice subsystem leftovers...
if exist "stonic\voice" rmdir /s /q "stonic\voice"
if exist "models" rmdir /s /q "models"
if exist "scripts\setup-voice.py" del /q "scripts\setup-voice.py"
if exist "scripts\verify-voice.py" del /q "scripts\verify-voice.py"
if exist "ui\components\AudioDevices.tsx" del /q "ui\components\AudioDevices.tsx"
if exist "VOICE_LANGUAGE_HOTFIX.txt" del /q "VOICE_LANGUAGE_HOTFIX.txt"
if exist "VOICE_QUALITY_V2_FIX.txt" del /q "VOICE_QUALITY_V2_FIX.txt"
if exist "VOICE_REBUILD_INSTALL.txt" del /q "VOICE_REBUILD_INSTALL.txt"
if exist ".runtime\voice-acceptance.json" del /q ".runtime\voice-acceptance.json"
if exist ".runtime\voice-fallback-acceptance.json" del /q ".runtime\voice-fallback-acceptance.json"

call uv sync --extra test
if errorlevel 1 goto failed
call npm.cmd ci
if errorlevel 1 goto failed
call npm.cmd run build
if errorlevel 1 goto failed
".venv\Scripts\python.exe" scripts\setup-integrations.py
if errorlevel 1 goto failed
echo STONIC is ready. Open Start-Stonic.cmd to launch.
pause
exit /b
:failed
echo Setup could not complete. Review the error above.
pause
exit /b 1
