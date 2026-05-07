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

REM Preflight: warn if ports are already in use so failures surface here.
set "PORT_API=8000"
set "PORT_WEB=5173"
for %%P in (%PORT_API% %PORT_WEB%) do (
  netstat -ano | findstr ":%%P " | findstr "LISTENING" >nul
  if !errorlevel! == 0 (
    echo [start.bat] WARNING: port %%P is already in use. The new process will likely fail to bind.
    echo [start.bat]          Close the existing window or kill the PID listed by:
    echo [start.bat]              netstat -ano ^| findstr ":%%P "
  )
)

echo [start.bat] Starting ARGUS API, worker, and frontend...

REM -u keeps Python's stdout unbuffered so uvicorn logs appear immediately.
REM Quoting %~dp0 protects against spaces in the project path.
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
