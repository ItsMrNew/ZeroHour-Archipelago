@echo off
cd /d "%~dp0"
if not "%~1"=="" goto console
if exist "%~dp0ZeroHourClient.exe" (
  start "" "%~dp0ZeroHourClient.exe"
) else (
  start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0ZeroHourClient.py"
)
exit /b
:console
if exist "%~dp0Diagnostics\ZeroHourClientConsole.exe" (
  "%~dp0Diagnostics\ZeroHourClientConsole.exe" %*
) else (
  "%~dp0.venv\Scripts\python.exe" "%~dp0ZeroHourConsole.py" %*
)
pause
