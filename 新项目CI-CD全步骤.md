# 新项目从零到 CI/CD：全部步骤（照着做）

> 目标：以后改代码，只要 `git push`，网站自己更新。  
> 用的方式和 Apex AI 一样。把「新项目名」「仓库名」换成你自己的。

下面假设：
- 你的 GitHub 用户名：`你的用户名`
- 新仓库名：`新项目`
- 服务器目录：`/opt/新项目`
- 网站端口：`8000`
- 服务器账号：`admin`
- 服务器 IP：`你的公网IP`

---

## 步骤 1：本机准备好项目

1. 电脑上有一个能跑的项目文件夹  
2. 打开终端，进入该文件夹  

---

## 步骤 2：在 GitHub 创建空仓库

1. 打开：https://github.com/new  
2. 仓库名填：`新项目`  
3. 不要勾选 README、gitignore、license  
4. 点创建  
5. 记下地址：`https://github.com/你的用户名/新项目.git`

---

## 步骤 3：本机上传代码到 GitHub

在项目文件夹执行：

```bash
git init
git add .
git commit -m "first commit"
git branch -M master
git remote add origin https://github.com/你的用户名/新项目.git
git push -u origin master
```

说明：
- 前 3 行：在本机保存版本  
- `remote add`：绑到 GitHub  
- `git push`：**上传到 GitHub**（这步最重要）

检查：浏览器打开仓库，能看到文件 = 成功。

---

## 步骤 4：服务器下载代码

1. 打开阿里云，远程连接服务器  
2. 执行：

```bash
sudo mkdir -p /opt/新项目
sudo chown -R admin:admin /opt/新项目
cd /opt/新项目
git clone https://github.com/你的用户名/新项目.git .
```

检查：`ls` 能看到项目文件。

---

## 步骤 5：服务器上先手工跑通网站

按你的技术栈安装（示例：前端 + Python 后端）：

```bash
cd /opt/新项目/frontend
npm install
npm run build

cd /opt/新项目/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

配置 `.env` 等密钥（不要提交到 Git）。

先临时启动试一下：

```bash
cd /opt/新项目/backend
source .venv/bin/activate
nohup python -m uvicorn main:app --host 0.0.0.0 --port 8000 > /tmp/新项目.log 2>&1 &
```

防火墙放行 `8000`。

浏览器打开：`http://你的公网IP:8000`  
**能打开再往下做。打不开就先别装自动部署。**

---

## 步骤 6：写一键部署脚本 deploy.sh

在本机项目根目录新建 `deploy.sh`（内容按项目改，下面是模板）：

```bash
#!/usr/bin/env bash
set -euo pipefail
APP_DIR=/opt/新项目
cd "$APP_DIR"

echo "[1] 拉代码"
git remote set-url origin https://github.com/你的用户名/新项目.git || true
git fetch origin master
git reset --hard origin/master

echo "[2] 构建前端"
cd "$APP_DIR/frontend"
npm config set registry https://registry.npmmirror.com
npm install
npm run build

echo "[3] 重启后端"
sudo systemctl restart 新项目
sleep 2
curl -s -o /dev/null -w "health:%{http_code}\n" http://127.0.0.1:8000/ || true
```

本机上传：

```bash
git add deploy.sh
git commit -m "add deploy.sh"
git push
```

服务器更新并试跑：

```bash
cd /opt/新项目
git pull
chmod +x deploy.sh
bash deploy.sh
```

---

## 步骤 7：用 systemd 托管后端（推荐）

本机建文件 `deploy/新项目.service`：

```ini
[Unit]
Description=新项目 backend
After=network.target

[Service]
Type=simple
User=admin
WorkingDirectory=/opt/新项目/backend
Environment=PATH=/opt/新项目/backend/.venv/bin:/usr/bin
ExecStart=/opt/新项目/backend/.venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=3
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

本机 push 后，服务器执行：

```bash
cd /opt/新项目
git pull
sudo cp deploy/新项目.service /etc/systemd/system/新项目.service
sudo systemctl daemon-reload
sudo systemctl enable --now 新项目
sudo systemctl status 新项目
```

能看到 `active` 即可。  
（之前临时 nohup 的进程可以停掉，改由 systemd 管。）

---

## 步骤 8：给新仓库安装 Runner

1. 打开：  
   `https://github.com/你的用户名/新项目/settings/actions/runners/new`  
2. 选 Linux、x64  
3. 服务器执行（**新目录，不要用 Apex 的 actions-runner**）：

```bash
mkdir -p ~/actions-runner-新项目
cd ~/actions-runner-新项目
```

4. 按网页上的命令下载、解压  
   （慢就本机下载再用 scp 传上来）  
5. 配置：

```bash
./config.sh --url https://github.com/你的用户名/新项目 --token 网页上的Token
```

一路回车。  

6. 启动服务：

```bash
sudo ./svc.sh install
sudo ./svc.sh start
```

7. 打开：  
   `https://github.com/你的用户名/新项目/settings/actions/runners`  
   看到 **Idle** = 成功。

---

## 步骤 9：加自动部署配置文件

本机项目里建文件夹和文件：

```text
.github/workflows/deploy.yml
```

内容：

```yaml
name: Deploy

on:
  push:
    branches: [master, main]
  workflow_dispatch:

jobs:
  deploy:
    runs-on: self-hosted
    steps:
      - name: Pull and restart
        run: |
          set -e
          cd /opt/新项目
          chmod +x deploy.sh
          bash deploy.sh
```

上传：

```bash
git add .github/workflows/deploy.yml
git commit -m "add cicd"
git push
```

---

## 步骤 10：验收自动部署

1. 随便改一个页面文字  
2. 执行：

```bash
git add .
git commit -m "test deploy"
git push
```

3. 打开：`https://github.com/你的用户名/新项目/actions`  
   - 绿勾 = 成功  
4. 打开：`http://你的公网IP:8000`  
   - 能看到改动 = 全部完成  

---

## 以后日常（新项目也一样）

```bash
git add .
git commit -m "说明"
git push
```

然后看 Actions + 网站。

---

## 对照清单（做完打勾）

- [ ] GitHub 有仓库，网页能看到代码  
- [ ] 服务器 `/opt/新项目` 有代码  
- [ ] 浏览器能打开网站  
- [ ] 有 `deploy.sh`，手动 `bash deploy.sh` 成功  
- [ ] systemd 服务是 active  
- [ ] Runner 是 Idle  
- [ ] 有 `.github/workflows/deploy.yml`  
- [ ] push 后 Actions 变绿，网站更新  

---

## 和 Apex AI 的区别（避免混）

| | Apex AI | 新项目 |
|--|---------|--------|
| 仓库 | 已有 c-sy1/ai-agent | 新建一个 |
| 服务器目录 | /opt/apex-ai | /opt/新项目 |
| Runner 目录 | ~/actions-runner | ~/actions-runner-新项目 |
| 要不要再走上面 1～10 步 | 不用（已做完） | 要 |

---

## 在哪查看

| 看什么 | 打开哪里 |
|--------|----------|
| 代码 | GitHub 仓库首页 |
| 部署成败 | 仓库 → Actions |
| Runner | Settings → Actions → Runners |
| 网站 | http://公网IP:8000 |
| 本说明文件 | 项目里的 `新项目CI-CD全步骤.md` |
