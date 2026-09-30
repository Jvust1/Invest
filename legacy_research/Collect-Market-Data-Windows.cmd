@echo off
setlocal
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 goto usepython
py -3 tools\collect_market_data.py wizard
goto finished
:usepython
python tools\collect_market_data.py wizard
:finished
echo.
echo Collection finished. Read the status above; success is not trading authorization.
pause
