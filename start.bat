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

REM Kill anything already bound to the API or web ports so Vite gets 5173
REM (otherwise it falls back to 5174 and CORS preflights from the wrong
REM origin start failing with 400). taskkill /F is fine — these are dev
REM servers, no data loss.
call :free_port %PORT_API% "API"
call :free_port %PORT_WEB% "web"

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


:free_port
REM %~1 = port number, %~2 = label for log line
set "_port=%~1"
set "_label=%~2"
set "_killed="
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":%_port% " ^| findstr "LISTENING"') do (
  if not "%%P"=="0" (
    if not defined _killed (
      echo [start.bat] Port %_port% (%_label%) busy — killing PID %%P
    ) else (
      echo [start.bat] Port %_port% (%_label%) busy — also killing PID %%P
    )
    taskkill /F /PID %%P >nul 2>&1
    set "_killed=1"
  )
)
if defined _killed (
  REM Brief pause so the kernel can release the socket before the new bind.
  timeout /t 1 /nobreak >nul
)
exit /b 0
