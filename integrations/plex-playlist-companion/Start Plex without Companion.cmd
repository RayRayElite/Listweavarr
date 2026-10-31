@echo off
echo Close Plex first. This removes only the companion loader; saved bookmarks and artwork are kept.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1" -Action disable
if errorlevel 1 (
  pause
  exit /b 1
)
start "" "%ProgramFiles%\Plex\Plex\Plex.exe"
