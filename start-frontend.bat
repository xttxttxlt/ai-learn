@echo off
chcp 65001 >/dev/null
setlocal
cd /d "%~dp0frontend"

where node >/dev/null 2>/dev/null
if errorlevel 1 (
    echo [ERROR] node not found. Please install Node.js and add it to PATH.
    if /I not "%AI_LEARN_NO_PAUSE%"=="1" pause
    exit /b 1
)

if not exist "node_modules" (
    echo [ERROR] frontend\node_modules not found. Run npm install first.
    if /I not "%AI_LEARN_NO_PAUSE%"=="1" pause
    exit /b 1
)

echo ==========================================
echo  AI Learn Frontend (WeChat Mini Program)
echo  Import into WeChat DevTools: %~dp0frontend
echo  Watching for changes...
echo ==========================================
echo.

call npm run dev:weapp
if /I not "%AI_LEARN_NO_PAUSE%"=="1" pause
