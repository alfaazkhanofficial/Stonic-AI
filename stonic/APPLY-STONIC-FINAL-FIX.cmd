@echo off
setlocal
cd /d "%~dp0"

echo.
echo ==============================================
echo   STONIC FINAL FIX - NO VOICE + xKiro RELIABILITY
echo ==============================================
echo.

echo [1/4] Removing the retired voice subsystem...
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

echo [2/4] Syncing the final Python dependency set...
where uv >nul 2>&1
if errorlevel 1 goto no_uv
call uv sync --extra test
if errorlevel 1 goto failed

echo [3/4] Rebuilding the desktop UI...
call npm.cmd run build
if errorlevel 1 goto failed

echo [4/4] Running backend verification...
".venv\Scripts\python.exe" -m pytest -q
if errorlevel 1 goto failed

echo.
echo STONIC final fix applied successfully.
echo Voice/STT/TTS is removed. xKiro provider/usage handling is updated.
echo You can now launch Start-Stonic.cmd.
echo.
pause
exit /b 0

:no_uv
echo uv was not found. Install uv or run your normal STONIC setup first.
pause
exit /b 1

:failed
echo.
echo The update stopped because a verification step failed.
echo Review the error above before building a release installer.
pause
exit /b 1
