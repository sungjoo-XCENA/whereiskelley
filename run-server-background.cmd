@echo off
cd /d "%~dp0"
set WHEREISKELLEY_HOST=127.0.0.1
set PYTHON_EXE=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe
if not exist "%PYTHON_EXE%" set PYTHON_EXE=python
"%PYTHON_EXE%" app.py
