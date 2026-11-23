@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo [1/2] 启动后端 API :8000 ...
start "Apex Backend" cmd /k "cd /d %~dp0backend && python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload"
timeout /t 2 /nobreak >nul
echo [2/2] 启动前端开发 :5173 （/api 已代理到 8000）...
cd frontend
npm run dev
