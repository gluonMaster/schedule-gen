@echo off
setlocal
cd /d "%~dp0"

set "PYTHON_EXE="
for /f "usebackq delims=" %%I in (`python -c "import sys; print(sys.executable)" 2^>nul`) do set "PYTHON_EXE=%%I"

if not defined PYTHON_EXE (
    echo python.exe not found in PATH
    pause
    exit /b 1
)

set "PYTHONW_EXE=%PYTHON_EXE:python.exe=pythonw.exe%"
if not exist "%PYTHONW_EXE%" set "PYTHONW_EXE=%PYTHON_EXE%"

start "" "%PYTHONW_EXE%" "%~dp0gui.py"
