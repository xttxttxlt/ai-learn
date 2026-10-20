@echo off
chcp 65001 >/dev/null
setlocal
cd /d "%~dp0"

echo Starting AI Learn backend and frontend...
start "AI Learn Backend" /D "%~dp0backend" "%~dp0start-backend.bat"
start "AI Learn Frontend" /D "%~dp0frontend" "%~dp0start-frontend.bat"

echo.
echo Two windows started:
echo   Backend: http://127.0.0.1:8000
echo   Frontend: import %~dp0frontend into WeChat DevTools
echo   Backend log: %~dp0backend\logs\backend.log
echo.
echo Close each window to stop the service.
if /I not "%AI_LEARN_NO_PAUSE%"=="1" pause
