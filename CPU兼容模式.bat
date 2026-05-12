@echo off
title HOMR GUI - CPU Safe Mode
color 0A

:: Switch to the directory of this script
cd /d "%~dp0"

echo ========================================================
echo               HOMR GUI (CPU Safe Mode)
echo ========================================================
echo.
echo Bypassing GPU acceleration...
echo Loading CPU execution environment. 
echo This mode is highly compatible with all computers.
echo.

:: Run the CPU version of the python script
"python_embed\python.exe" "homr_gui_cpu.py"

:: Pause if the program crashes so you can read the error
echo.
pause