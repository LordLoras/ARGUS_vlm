@echo off
setlocal

cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" "%~dp0scripts\stop_argus.py" %*
) else (
  python "%~dp0scripts\stop_argus.py" %*
)

endlocal
