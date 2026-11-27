#!/usr/bin/env bash
# Apex AI 一键部署（服务器执行；也可被 GitHub Actions 通过 SSH 调用）
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/apex-ai}"
cd "$APP_DIR"

echo "[1/4] git sync (GitHub)"
git remote set-url origin https://github.com/c-sy1/ai-agent.git || true
git fetch origin master
# 丢弃服务器上对已跟踪文件的本地改动，避免挡住更新（.env / keys 一般在 .gitignore）
git reset --hard origin/master
git clean -fd -e backend/.env -e backend/keys -e backend/apex_ai.db -e backend/.venv -e frontend/node_modules


echo "[2/4] 构建前端"
cd "$APP_DIR/frontend"
npm config set registry https://registry.npmmirror.com
npm install
npm run build

echo "[3/4] 重启后端（systemd）"
cd "$APP_DIR/backend"
# 首次或更新后安装/刷新 unit
if [[ -f "$APP_DIR/deploy/apex-ai.service" ]]; then
  sudo cp "$APP_DIR/deploy/apex-ai.service" /etc/systemd/system/apex-ai.service
  sudo systemctl daemon-reload
  sudo systemctl enable apex-ai.service >/dev/null 2>&1 || true
fi
# 停掉旧的 nohup 进程，改由 systemd 托管
pkill -f "uvicorn main:app" || true
sleep 1
sudo systemctl restart apex-ai.service
sleep 2
sudo systemctl --no-pager --full status apex-ai.service || true

echo "[4/4] 部署完成"
echo "日志：journalctl -u apex-ai -f  或  /tmp/apex-ai.log"
echo "访问：http://39.106.162.243:8000"
curl -s -o /dev/null -w "health:%{http_code}\n" http://127.0.0.1:8000/ || true
