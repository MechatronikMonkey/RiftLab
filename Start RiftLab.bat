@echo off
setlocal enableextensions
title RiftLab Viewer

rem ===================================================================
rem  RiftLab viewer launcher - just double-click this file.
rem  Opens the interactive viewer with an empty window; use
rem  "Open .sqlite..." inside it to load a recorded session.
rem ===================================================================

rem Always work from this script's own folder (the RiftLab folder),
rem no matter where it is double-clicked from.
cd /d "%~dp0"

rem --- pick a Python: a local .venv if present, else one on PATH ------
set "PY="
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if not defined PY ( where py >nul 2>nul && set "PY=py" )
if not defined PY ( where python >nul 2>nul && set "PY=python" )
if not defined PY (
    echo.
    echo   Python was not found on this PC.
    echo   Install Python 3.11 or newer from https://www.python.org/downloads/
    echo   During setup, tick "Add python.exe to PATH", then run this file again.
    echo.
    pause
    exit /b 1
)

rem --- make sure the GUI packages are available (install once if not) -
"%PY%" -c "import PySide6, pyqtgraph" >nul 2>nul
if errorlevel 1 (
    echo.
    echo   Installing the required packages ^(one-time, needs internet^)...
    echo.
    "%PY%" -m pip install -r requirements.txt
    if errorlevel 1 goto setup_failed
)

rem --- launch the viewer detached, then close this window ------------
rem prefer a windowed interpreter (no console). Last matching line wins, so
rem the order is: .venv pythonw > pythonw > pyw > the console Python.
set "PYW=%PY%"
where pyw >nul 2>nul && set "PYW=pyw"
where pythonw >nul 2>nul && set "PYW=pythonw"
if exist ".venv\Scripts\pythonw.exe" set "PYW=.venv\Scripts\pythonw.exe"
start "" "%PYW%" -m riftlab gui
exit /b 0

:setup_failed
echo.
echo   Setup failed. Check your internet connection and try again.
echo.
pause
exit /b 1
