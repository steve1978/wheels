@echo off
title Wheels - stopping
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop.ps1"
echo.
pause
