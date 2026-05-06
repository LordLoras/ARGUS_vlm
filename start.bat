@echo off
setlocal

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Missing .venv\Scripts\python.exe
  exit /b 1
)

if not exist "config.yaml" (
  copy "config.example.yaml" "config.yaml" >nul
  echo Created config.yaml from config.example.yaml
)

echo Starting AdScope Local API, worker, and frontend...

start "AdScope API" cmd /k ".venv\Scripts\python.exe -m ad_classifier api --host 127.0.0.1 --port 8000"
start "AdScope Worker" cmd /k ".venv\Scripts\python.exe -m ad_classifier worker"

if exist "frontend\node_modules" (
  start "AdScope Frontend" cmd /k "cd /d %~dp0frontend && npm run dev"
) else (
  echo Frontend dependencies are not installed. Run:
  echo   cd frontend
  echo   npm install
  echo   npm run dev
)

echo API:      http://127.0.0.1:8000
echo Frontend: http://127.0.0.1:5173

endlocal
