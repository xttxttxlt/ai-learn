@echo off
chcp 65001 >/dev/null
setlocal
cd /d "%~dp0backend"

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] backend\.venv\Scripts\python.exe not found.
    echo Please install backend dependencies first.
    if /I not "%AI_LEARN_NO_PAUSE%"=="1" pause
    exit /b 1
)

echo ==========================================
echo  AI Learn Backend
echo  URL: http://127.0.0.1:8000
echo  Log: %~dp0backend\logs\backend.log
echo ==========================================
echo.

.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --log-level info
if /I not "%AI_LEARN_NO_PAUSE%"=="1" pause
