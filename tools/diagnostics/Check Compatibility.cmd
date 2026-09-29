@echo off
setlocal
set /p "zh_game_dat=Full path to Zero Hour Game.dat (without quotes): "
if not defined zh_game_dat exit /b 1
if exist "%~dp0ZeroHourClientConsole.exe" (
  cd /d "%~dp0.."
  "%~dp0ZeroHourClientConsole.exe" --check-executable "%zh_game_dat%"
) else (
  cd /d "%~dp0..\.."
  "%~dp0..\..\.venv\Scripts\python.exe" "%~dp0..\..\ZeroHourConsole.py" --check-executable "%zh_game_dat%"
)
set "zh_exit_code=%errorlevel%"
pause
exit /b %zh_exit_code%
