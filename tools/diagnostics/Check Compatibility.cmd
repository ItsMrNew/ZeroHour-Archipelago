@echo off
setlocal
set /p "zh_game_dat=Full path to Zero Hour Game.dat (without quotes): "
if not defined zh_game_dat exit /b 1
call "%~dp0..\..\Start Client.cmd" --check-executable "%zh_game_dat%"
