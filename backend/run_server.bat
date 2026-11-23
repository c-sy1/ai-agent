@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Apex AI 服务 - 请勿关闭
color 0A
echo.
echo  Apex AI 正在运行
echo  浏览器访问: http://127.0.0.1:8000
echo  关闭本窗口将停止服务
echo.
python -m uvicorn main:app --host 127.0.0.1 --port 8000
echo.
pause
