@echo off
setlocal EnableDelayedExpansion

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [start.bat] Missing .venv\Scripts\python.exe
  echo [start.bat] Create the venv and install deps before running this script.
  exit /b 1
)

if not exist "config.yaml" (
  copy "config.example.yaml" "config.yaml" >nul
  echo [start.bat] Created config.yaml from config.example.yaml
)

set "PORT_API=8000"
set "PORT_WEB=5173"

REM Kill leftover processes before starting new ones.
call :kill_existing

echo [start.bat] Starting ARGUS API, worker, and frontend...

REM -u keeps Python's stdout unbuffered so uvicorn logs appear immediately.
start "ARGUS API" cmd /k "cd /d "%~dp0" && echo [api] launching uvicorn on http://127.0.0.1:%PORT_API% && "%~dp0.venv\Scripts\python.exe" -u -m ad_classifier api --host 127.0.0.1 --port %PORT_API%"
start "ARGUS Worker" cmd /k "cd /d "%~dp0" && echo [worker] launching SQLite-backed worker && "%~dp0.venv\Scripts\python.exe" -u -m ad_classifier worker"

if exist "frontend\node_modules" (
  start "ARGUS Frontend" cmd /k "cd /d "%~dp0frontend" && echo [web] vite dev on http://127.0.0.1:%PORT_WEB% && npm run dev"
) else (
  echo [start.bat] Frontend dependencies are not installed. Run:
  echo   cd frontend
  echo   npm install
  echo   npm run dev
)

echo.
echo [start.bat] API:      http://127.0.0.1:%PORT_API%
echo [start.bat] Frontend: http://127.0.0.1:%PORT_WEB%
echo [start.bat] First run can take 10-30s while Python warms up imports.
echo [start.bat] Each component lives in its own cmd window. Close those to stop.

endlocal
exit /b 0


:kill_existing
REM Kill stale API, worker, and Vite processes.
REM 1. Port-based kill for API and Vite (they bind TCP ports).
call :free_port %PORT_API% API
call :free_port %PORT_WEB% web

REM 2. Process-based kill for the worker (no TCP port to probe).
REM    Match on "ad_classifier worker" in the command line so we
REM    don't accidentally kill unrelated Python processes.
set "_wk_killed="
for /f "tokens=2" %%P in ('wmic process where "commandline like '%%ad_classifier worker%%'" get processid /format:value 2^>nul ^| findstr /r "[0-9]"') do (
  echo [start.bat] Killing stale worker PID %%P
  taskkill /F /PID %%P >nul 2>&1
  set "_wk_killed=1"
)
if defined _wk_killed timeout /t 1 /nobreak >nul
exit /b 0


:free_port
REM %~1 = port number, %~2 = label (no spaces)
set "_port=%~1"
set "_label=%~2"
set "_killed_any="
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":%_port% " ^| findstr "LISTENING"') do call :kill_pid %%P %_port% %_label%
if defined _killed_any timeout /t 1 /nobreak >nul
exit /b 0


:kill_pid
REM %~1 = pid, %~2 = port, %~3 = label
if "%~1"=="0" exit /b 0
echo [start.bat] Port %~2 [%~3] busy. Killing PID %~1
taskkill /F /PID %~1 >nul 2>&1
set "_killed_any=1"
exit /b 0