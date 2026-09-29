@echo off
setlocal
echo Sends one DeathLink to linked players in the selected room.
if exist "%~dp0ZeroHourClientConsole.exe" (
  cd /d "%~dp0.."
  "%~dp0ZeroHourClientConsole.exe" --send-deathlink-test --slot DeathLinkTester
) else (
  cd /d "%~dp0..\.."
  "%~dp0..\..\.venv\Scripts\python.exe" "%~dp0..\..\ZeroHourConsole.py" --send-deathlink-test --slot DeathLinkTester
)
set "zh_exit_code=%errorlevel%"
pause
exit /b %zh_exit_code%
