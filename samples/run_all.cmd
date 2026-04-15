@echo off
setlocal
cd /d "%~dp0.."
set PYTHONPATH=%~dp0..\src
python samples/run_all.py
endlocal
pause
