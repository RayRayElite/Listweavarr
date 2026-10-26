@echo off
cd /d "%~dp0"
set "LISTWEAVARR_CURATOR_MODE=1"
python app.py
pause
