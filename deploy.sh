#!/usr/bin/env bash
# Apex AI 一键部署（服务器执行；也可被 GitHub Actions 通过 SSH 调用）
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/apex-ai}"
cd "$APP_DIR"

echo "[1/4] git pull (GitHub)"
git remote set-url origin https://github.com/c-sy1/ai-agent.git || true
git pull --ff-only origin master || git pull origin master || git pull


echo "[2/4] 构建前端"
cd "$APP_DIR/frontend"
npm config set registry https://registry.npmmirror.com
npm install
npm run build

echo "[3/4] 重启后端"
cd "$APP_DIR/backend"
# shellcheck disable=SC1091
source .venv/bin/activate
pkill -f "uvicorn main:app" || true
nohup python -m uvicorn main:app --host 0.0.0.0 --port 8000 > /tmp/apex-ai.log 2>&1 &

echo "[4/4] 部署完成"
echo "日志：/tmp/apex-ai.log"
echo "访问：http://39.106.162.243:8000"
pgrep -af "uvicorn main:app" || true
