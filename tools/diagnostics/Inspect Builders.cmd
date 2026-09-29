@echo off
setlocal
if exist "%~dp0ZeroHourClientConsole.exe" (
  cd /d "%~dp0.."
  "%~dp0ZeroHourClientConsole.exe" --diagnose-builders
) else (
  cd /d "%~dp0..\.."
  "%~dp0..\..\.venv\Scripts\python.exe" "%~dp0..\..\ZeroHourConsole.py" --diagnose-builders
)
set "zh_exit_code=%errorlevel%"
pause
exit /b %zh_exit_code%
