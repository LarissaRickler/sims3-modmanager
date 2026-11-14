@echo off
cd /d "%~dp0"
py -3 -c "import tkinter" >nul 2>&1
if errorlevel 1 (
  echo Python 3.11 oder neuer mit Tcl/Tk wird benoetigt.
  echo Installation: https://www.python.org/downloads/windows/
  pause
  exit /b 1
)
py -3 app.py
if errorlevel 1 pause
