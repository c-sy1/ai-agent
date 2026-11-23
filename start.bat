@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 正在更新前端页面...
cd frontend
call npm run build
cd ..
echo 正在启动服务...
call "%~dp0启动服务.bat"
