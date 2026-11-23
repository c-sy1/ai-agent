@echo off
chcp 65001 >nul
cd /d "%~dp0"

powershell -NoProfile -Command "try { (Invoke-WebRequest 'http://127.0.0.1:8000/api/health' -UseBasicParsing -TimeoutSec 2).StatusCode | Out-Null; exit 0 } catch { exit 1 }" >nul 2>&1
if %errorlevel%==0 (
  start "" "http://127.0.0.1:8000/"
  exit /b 0
)

start "Apex AI 服务" cmd /k "%~dp0backend\run_server.bat"

:wait
timeout /t 2 /nobreak >nul
powershell -NoProfile -Command "try { (Invoke-WebRequest 'http://127.0.0.1:8000/api/health' -UseBasicParsing -TimeoutSec 3).StatusCode | Out-Null; exit 0 } catch { exit 1 }" >nul 2>&1
if %errorlevel%==0 goto open
goto wait

:open
start "" "http://127.0.0.1:8000/"
exit /b 0
