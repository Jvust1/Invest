@echo off
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  python -m invest --open
) else (
  py -3 -m invest --open
)
pause
