@echo off
title Wheels - describing wheel designs (AI captioner)
setlocal
cd /d "%~dp0backend"

echo.
echo   Wheels - AI wheel-design captioner
echo   -----------------------------------
echo   Writes a one-line design description for every catalog wheel that
echo   doesn't have one yet. Run it again whenever you add new wheels.
echo.
echo   NOTE: this needs the graphics card, so the app will be STOPPED first.
echo   A full first run over the whole catalog can take a couple of hours.
echo.
set /p GO="  Continue? [Y/n]: "
if /i "%GO%"=="n" exit /b 0

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop.ps1"
echo.

".venv\Scripts\python.exe" caption_wheels.py %*

echo.
echo   Finished. Double-click start.bat to bring the app back up.
pause
