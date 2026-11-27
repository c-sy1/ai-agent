# Apex AI · CI/CD 自动部署完整说明

> 答辩 / 汇报可直接照着讲。当前主仓库在 **GitHub**，云主机是阿里云**轻量应用服务器**。

---

## 一、这是什么？有什么用？

**CI/CD** = 持续集成 / 持续部署。

对本项目来说就是：

> 你在电脑上改完代码 → `git push` 到 GitHub → **云服务器自动拉代码、重新构建前端、重启后端** → 网站变成新版本。

### 有什么用？

| 作用 | 说明 |
|------|------|
| 少手工操作 | 不用每次登录服务器敲命令 |
| 版本可追溯 | 每次部署对应一次 Git 提交 |
| 演示加分 | 体现工程化：代码托管 + 自动发布 |
| 和「只跑本地」的区别 | 老师/同学打开公网地址看到的是刚发布的版本 |

**一句话：** 自动部署 = 把「发版」从手工变成流水线。

---

## 二、整体流程（怎么跑起来的）

```
本机改代码
    ↓
git add . / git commit / git push
    ↓
代码到达 GitHub（https://github.com/c-sy1/ai-agent）
    ↓
GitHub Actions 触发工作流：Deploy to Aliyun ECS
    ↓
任务发到云主机上的「自托管 Runner」（self-hosted）
    ↓
Runner 执行：cd /opt/apex-ai && bash deploy.sh
    ↓
deploy.sh：同步代码 → npm 构建前端 → systemctl 重启后端
    ↓
网站更新：http://39.106.162.243:8000
```

### 为什么用「自托管 Runner」？

GitHub 官方云端 Runner 在国外，用 SSH 连国内轻量服务器经常被挡。  
所以在 **服务器本机** 装了一个 Runner：机器自己连 GitHub 领任务，不需要境外 SSH 打进来。

---

## 三、关键文件在仓库哪里？

| 文件 | 路径 | 干什么 |
|------|------|--------|
| 工作流定义 | `.github/workflows/deploy.yml` | 规定：push 到 master 就部署；在 self-hosted 上跑 |
| 部署脚本 | `deploy.sh` | 拉代码、构建前端、重启服务 |
| 后端服务配置 | `deploy/apex-ai.service` | systemd：挂了自动重启 uvicorn |

仓库地址：**https://github.com/c-sy1/ai-agent**

---

## 四、在网页上「哪里能看到」？

### 1. 看自动部署有没有成功

- 打开：https://github.com/c-sy1/ai-agent/actions  
- 或：仓库页顶部点 **Actions（行动）**  
- 点最新一次 **Deploy to Aliyun ECS**：绿勾 = 成功，红叉 = 失败  

### 2. 看 Runner（执行机器）是否在线

- 打开：https://github.com/c-sy1/ai-agent/settings/actions/runners  
- 或：仓库 **Settings → Actions → Runners**  
- 应看到一台机器，状态 **Idle（空闲）** 或 **Active（忙碌）**  

### 3. 看 Secrets（密钥，一般不用常改）

- 打开：https://github.com/c-sy1/ai-agent/settings/secrets/actions  
- 或：Settings → Secrets and variables → Actions  
- 曾配置过：`ECS_HOST` / `ECS_USER` / `ECS_SSH_KEY`（现以自托管 Runner 为主，SSH 方案备用）

### 4. 看网站是否已更新

- 地址：**http://39.106.162.243:8000**（必须带 **:8000**）  
- 改完前端后建议 **Ctrl + F5** 强刷  

### 5. 在服务器上看服务是否在跑（可选）

阿里云轻量 → 远程连接 Workbench，执行：

```bash
systemctl status apex-ai
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/
```

`active` 且返回 `200` 即正常。

---

## 五、你日常只要做什么？

在项目目录：

```bash
git add .
git commit -m "说明这次改了什么"
git push
```

然后去 **Actions** 看是否变绿，再打开网站验证。

> 若提示 `nothing to commit, working tree clean`：说明没有新改动，不是被取消，只是没东西可提交。

---

## 六、服务器上相关位置

| 位置 | 说明 |
|------|------|
| `/opt/apex-ai` | 网站代码目录 |
| `/home/admin/actions-runner` | GitHub Actions Runner 安装目录 |
| `apex-ai.service` | systemd 服务名（`systemctl status apex-ai`） |

---

## 七、常见情况怎么理解？

| 现象 | 含义 |
|------|------|
| Actions 显示 Queued | 在排队，Runner 忙或刚接任务，稍等 |
| Actions 红叉，网站还能开 | 多半是服务器拉 GitHub 超时；可再 push 或手动在服务器跑 `bash /opt/apex-ai/deploy.sh` |
| 打开 IP 空白 / ERR_EMPTY_RESPONSE | 检查是否漏了 **:8000**；或服务正在重启，等几秒再刷 |
| 部署瞬间打不开 | 正常：重启后端会有短暂中断，systemd 会自动拉起 |

---

## 八、答辩可以怎么说（30 秒）

「我们把代码放在 GitHub。每次推送到 master，会触发 Actions 流水线。执行器装在阿里云轻量服务器上（自托管 Runner），自动执行 deploy.sh：同步代码、构建前端、用 systemd 重启后端。这样形成完整的 CI/CD：提交即发布，并可在 Actions 页面查看每次部署结果。」

---

## 九、和 Gitee 的关系（了解即可）

- **现在主流程：GitHub → 自托管 Runner → 自动部署**  
- 以前用过 **Gitee Go**；Gitee 仓库还可作备份（远程名一般是 `gitee`）  
- 本机默认 `git push` 推的是 GitHub（`origin`）

---

## 十、如果是一个「新项目」要从零部署（一步一步）

下面按「国内轻量服务器 + GitHub + 自动部署」来写，和本项目同类。

### 第 0 步：准备什么

- 一台云服务器（阿里云轻量 / ECS），有公网 IP  
- 本机已装 Git、能打开 GitHub  
- 项目能在本地跑通（前端能 build、后端能启动）

---

### 第 1 步：代码放进 Git，推到 GitHub

在本机项目目录：

```bash
git init
git add .
git commit -m "first commit"
```

浏览器打开 https://github.com/new  
- 新建空仓库（不要勾 README）  
- 复制仓库地址，例如 `https://github.com/你的用户名/项目名.git`

```bash
git branch -M master
git remote add origin https://github.com/你的用户名/项目名.git
git push -u origin master
```

**在哪看：** GitHub 仓库首页应能看到代码。

---

### 第 2 步：服务器上先「手工部署通」

用阿里云 **远程连接 / Workbench** 登录服务器：

```bash
# 例：放到 /opt/你的项目
sudo mkdir -p /opt/你的项目
sudo chown -R $USER:$USER /opt/你的项目
cd /opt/你的项目
git clone https://github.com/你的用户名/项目名.git .
```

然后按项目需要安装依赖并启动，例如：

```bash
# 前端
cd frontend && npm install && npm run build

# 后端（示例）
cd ../backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# 配置 .env、密钥等（不要提交到 Git）
nohup python -m uvicorn main:app --host 0.0.0.0 --port 8000 &
```

防火墙放行业务端口（如 `8000`、`80`）。

浏览器访问：`http://公网IP:端口`，**先确认手工部署能打开**，再做自动部署。

---

### 第 3 步：写一键部署脚本 `deploy.sh`

在仓库根目录放 `deploy.sh`（内容按你的技术栈改），大意是：

1. `git fetch` + `git reset --hard origin/master`  
2. 构建前端  
3. 重启后端  

推到 GitHub：

```bash
git add deploy.sh
git commit -m "add deploy.sh"
git push
```

在服务器试跑一次：

```bash
cd /opt/你的项目
bash deploy.sh
```

---

### 第 4 步：用 systemd 托管后端（推荐，防挂死）

新建 `deploy/xxx.service`，安装到服务器：

```bash
sudo cp /opt/你的项目/deploy/xxx.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now xxx
sudo systemctl status xxx
```

`deploy.sh` 里用 `sudo systemctl restart xxx` 代替裸 `pkill` + `nohup`。

---

### 第 5 步：装 GitHub 自托管 Runner（国内服务器推荐）

1. 打开：`https://github.com/你的用户名/项目名/settings/actions/runners/new`  
2. 选 **Linux**、**x64**  
3. 在服务器执行页面给出的下载 / 解压 / `./config.sh` / `./svc.sh install` / `./svc.sh start`  
   - Token 用页面上的  
   - 若 GitHub 下载很慢：可在本机下好安装包再用 `scp` 传到服务器  

4. 在 **Settings → Actions → Runners** 看到状态 **Idle**  

> 说明：国外官方 Runner 用 SSH 打国内机器经常失败，所以 runner 装在服务器本机更稳。

---

### 第 6 步：加 Actions 工作流

仓库里建文件：`.github/workflows/deploy.yml`

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
          cd /opt/你的项目
          chmod +x deploy.sh
          bash deploy.sh
```

提交并推送：

```bash
git add .github/workflows/deploy.yml
git commit -m "add github actions deploy"
git push
```

---

### 第 7 步：验证自动部署

1. 随便改一行说明文字，再：

```bash
git add .
git commit -m "test auto deploy"
git push
```

2. 打开 **Actions**，看是否绿勾  
3. 打开网站，确认已更新  

---

### 新项目清单（对照用）

- [ ] GitHub 有仓库且能 push  
- [ ] 服务器 `git clone` 后手动能访问网站  
- [ ] 有 `deploy.sh` 且手动执行成功  
- [ ] systemd（或同类）托管进程，挂了会重启  
- [ ] 防火墙放行端口  
- [ ] 自托管 Runner 显示 Idle  
- [ ] `.github/workflows/deploy.yml` 存在  
- [ ] push 后 Actions 成功、网站变新  

---

### 新项目「在哪找什么」

| 要找的东西 | 位置 |
|------------|------|
| 代码 | GitHub 仓库 |
| 部署是否成功 | 仓库 → Actions |
| Runner | Settings → Actions → Runners |
| 工作流文件 | `.github/workflows/*.yml` |
| 部署脚本 | 仓库根目录 `deploy.sh` |
| 服务器代码 | 一般 `/opt/项目名` |
| 网站 | `http://公网IP:端口` |
