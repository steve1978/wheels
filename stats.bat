@echo off
title Wheels - stats
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stats.ps1"
echo.
pause
