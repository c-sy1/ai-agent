# Apex AI · CI/CD 自动部署完整说明（全流程）

本文包含：**从 GitHub 创建仓库并上传代码 → 服务器部署 → 自动发布 → 本项目日常怎么用 → 在哪查看**。答辩和以后新项目都可以对照。

---

# 第一部分：这是什么？有什么用？

**CI/CD** = 持续集成 / 持续部署。

对网站项目来说就是：

> 改完代码 → 上传到 GitHub → **云服务器自动更新网站**。

| 作用 | 说明 |
|------|------|
| 少手工 | 少登录服务器拷文件、敲命令 |
| 可追溯 | 每次上线对应一次 Git 提交 |
| 工程化 | 答辩可讲「提交即发布」 |
| 协作 | 代码在 GitHub，别人也能看到版本历史 |

**一句话：** 自动部署 = 把「发版」变成流水线。

---

# 第二部分：从「创建 GitHub 仓库」到「上传代码」（必会）

> 这就是「把代码放到 GitHub」的完整意思。  
> **创建仓库**在网页上做；**上传代码**用 `git push`。

## 流程总览

```
① 浏览器：在 GitHub 创建一个空仓库
        ↓
② 本机：用 Git 把项目做成版本（init / add / commit）
        ↓
③ 本机：关联远程仓库地址（git remote add）
        ↓
④ 本机：git push  ← 这一步才叫「上传到 GitHub」
        ↓
⑤ 打开 GitHub 网页，能看到你的文件 = 上传成功
```

---

## 第 1 步：在 GitHub 网页创建仓库

1. 打开：https://github.com/new  
2. **Repository name** 填名字，例如 `ai-agent`  
3. 选 Public 或 Private  
4. **不要勾** Add README / .gitignore / license（保持空仓，方便第一次推送）  
5. 点 **Create repository**  

创建后页面会给出地址，例如：

`https://github.com/你的用户名/ai-agent.git`

**在哪看：** 浏览器打开该地址，若还是空的，说明还没上传代码（正常）。

---

## 第 2 步：本机把项目交给 Git 管理

进入你的项目文件夹（示例）：

```bash
cd 你的项目目录
```

执行：

```bash
git init
git add .
git commit -m "first commit"
```

| 命令 | 意思 |
|------|------|
| `git init` | 让这个文件夹开始被 Git 管理 |
| `git add .` | 把当前所有文件选进「待提交」 |
| `git commit -m "..."` | 在**本机**存成一个版本 |

⚠️ 这三步 **还没有上传到 GitHub**，只在你电脑里。

---

## 第 3 步：告诉 Git「远程仓库在哪」

```bash
git branch -M master
git remote add origin https://github.com/你的用户名/ai-agent.git
```

| 命令 | 意思 |
|------|------|
| `git branch -M master` | 主分支名叫 master |
| `git remote add origin 地址` | 起名 `origin`，指向你刚创建的 GitHub 仓库 |

（若提示 remote origin 已存在，说明以前加过，可跳过或先 `git remote -v` 查看。）

---

## 第 4 步：上传到 GitHub（真正的「上传」）

```bash
git push -u origin master
```

| 命令 | 意思 |
|------|------|
| `git push` | 把本机提交传到 GitHub |
| `-u origin master` | 第一次指定推到 origin 的 master，并记住默认 |

浏览器刷新你的仓库页面，**能看到文件 = 上传成功**。

---

## 以后每次改代码再上传（更新仓库）

```bash
git add .
git commit -m "说明改了什么"
git push
```

这就是「再次上传更新」，不是重新创建仓库。

---

# 第三部分：服务器部署（让公网能打开网站）

代码在 GitHub 之后，还要放到云服务器上跑起来。

## 第 5 步：服务器克隆代码

阿里云远程连接（Workbench）登录后：

```bash
sudo mkdir -p /opt/apex-ai
sudo chown -R $USER:$USER /opt/apex-ai
cd /opt/apex-ai
git clone https://github.com/你的用户名/ai-agent.git .
```

| 命令 | 意思 |
|------|------|
| `mkdir` | 建目录 |
| `git clone 地址 .` | 从 GitHub **下载**代码到当前目录 |

---

## 第 6 步：安装依赖并启动（先手工跑通）

```bash
# 前端
cd /opt/apex-ai/frontend
npm install
npm run build

# 后端
cd /opt/apex-ai/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# 配置 .env、密钥（不要提交到 Git）
```

启动后端（早期可用 nohup；本项目后来改成 systemd，见后文）：

```bash
nohup python -m uvicorn main:app --host 0.0.0.0 --port 8000 &
```

轻量服务器 **防火墙** 放行端口 `8000`（以及需要的 22/80 等）。

浏览器打开：`http://公网IP:8000`，能打开再继续做自动部署。

---

## 第 7 步：写一键脚本 deploy.sh

仓库根目录的 `deploy.sh` 负责：

1. 从 GitHub 拉最新代码  
2. 构建前端  
3. 重启后端  

本机改好后同样 `add` / `commit` / `push`。服务器上可先手动试：

```bash
cd /opt/apex-ai
bash deploy.sh
```

---

## 第 8 步：systemd 托管后端（防挂死）

本项目文件：`deploy/apex-ai.service`

```bash
sudo cp /opt/apex-ai/deploy/apex-ai.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now apex-ai
sudo systemctl status apex-ai
```

| 命令 | 意思 |
|------|------|
| `enable` | 开机自启 |
| `restart` / `status` | 重启 / 查看是否在跑 |

挂了会自动拉起，比单纯 `nohup` 稳。

---

# 第四部分：接上 CI/CD（push 就自动部署）

## 第 9 步：安装 GitHub 自托管 Runner

为何自托管：国外官方 Runner SSH 进国内轻量机经常失败；Runner 装在服务器上，由机器主动领任务更稳。

1. 打开：`https://github.com/你的用户名/仓库名/settings/actions/runners/new`  
2. 选 **Linux**、**x64**  
3. 在服务器执行页面上的下载、解压、`./config.sh`、`sudo ./svc.sh install`、`sudo ./svc.sh start`  
4. 在 **Settings → Actions → Runners** 看到 **Idle**

（下载慢时可本机下好再用 `scp` 传到服务器。）

---

## 第 10 步：添加 Actions 工作流

文件：`.github/workflows/deploy.yml`  

含义：向 `master` push 时，在 self-hosted Runner 上执行 `deploy.sh`。

推送该文件后，以后每次：

```bash
git add .
git commit -m "说明"
git push
```

就会自动部署。

---

## 自动部署链路（串起来）

```
本机 git push
    → GitHub 仓库更新
    → Actions 触发
    → 服务器 Runner 跑 deploy.sh
    → 同步代码 + 构建前端 + systemctl 重启
    → 网站 http://公网IP:8000 更新
```

---

# 第五部分：本项目 Apex AI（已经配好的现状）

> 上面第二～四部分是「从零怎么做」。  
> **Apex AI 这些已经做完**，你不用再建仓、再装一遍 Runner。

| 项目 | 状态 | 地址 |
|------|------|------|
| GitHub 仓库 | ✅ | https://github.com/c-sy1/ai-agent |
| 线上网站 | ✅ | http://39.106.162.243:8000 |
| 服务器代码 | ✅ | `/opt/apex-ai` |
| Runner | ✅ | Settings → Actions → Runners |
| 工作流 | ✅ | `.github/workflows/deploy.yml` |
| 部署脚本 | ✅ | `deploy.sh` |
| 后端服务 | ✅ | `systemctl status apex-ai` |

### 本项目日常只需

在目录 `C:\Users\lenovo\Desktop\项目总和\AI智能体原型`：

```bash
git add .
git commit -m "说明这次改了什么"
git push
```

然后看：

- 部署结果：https://github.com/c-sy1/ai-agent/actions  
- 网站：http://39.106.162.243:8000 （带 `:8000`，建议 Ctrl+F5）

---

# 第六部分：在哪可以找到什么？

| 要找什么 | 在哪 |
|----------|------|
| 创建/查看仓库 | https://github.com/c-sy1/ai-agent |
| 是否上传成功 | 打开仓库网页看有没有文件 |
| 每次部署成败 | https://github.com/c-sy1/ai-agent/actions |
| Runner 是否在线 | https://github.com/c-sy1/ai-agent/settings/actions/runners |
| Secrets（旧 SSH 方案） | Settings → Secrets and variables → Actions |
| 工作流代码 | 仓库 `.github/workflows/deploy.yml` |
| 部署脚本 | 仓库根目录 `deploy.sh` |
| systemd 配置 | `deploy/apex-ai.service` |
| 本机项目 | `桌面\项目总和\AI智能体原型` |
| 服务器项目 | `/opt/apex-ai` |
| Runner 安装目录 | `/home/admin/actions-runner` |
| 线上访问 | http://39.106.162.243:8000 |

---

# 第七部分：常用命令含义速查

| 命令 | 意思 |
|------|------|
| `git init` | 本机开始用 Git 管理项目 |
| `git add .` | 选中改动 |
| `git commit -m "..."` | 本机保存一个版本 |
| `git remote add origin 网址` | 绑定 GitHub 仓库地址 |
| `git push` | **上传到 GitHub** |
| `git clone 网址` | 从 GitHub 下载到服务器 |
| `git fetch` / `git reset --hard` | 部署时对齐远程最新代码 |
| `npm install` / `npm run build` | 装前端依赖 / 打包前端 |
| `systemctl restart apex-ai` | 重启本项目后端 |
| `bash deploy.sh` | 一键部署 |

---

# 第八部分：常见现象

| 现象 | 含义 |
|------|------|
| `nothing to commit, working tree clean` | 没有新改动，不是被取消 |
| Actions Queued | 排队中，稍等 |
| Actions 红叉但网站还能开 | 多半服务器拉 GitHub 超时；可再 push 或服务器上 `bash /opt/apex-ai/deploy.sh` |
| 打开 IP 没页面 | 检查是否漏了 **:8000** |
| 部署瞬间打不开 | 重启服务的短暂中断，systemd 会拉起 |

---

# 第九部分：答辩 30 秒

「代码托管在 GitHub。创建仓库并 push 上传后，服务器克隆运行。我们配置了自托管 Runner 与 Actions：每次 push master 自动执行 deploy.sh，构建前端并用 systemd 重启后端，形成完整 CI/CD。Actions 页面可查看发布记录，公网可访问最新站点。」

---

# 第十部分：和 Gitee 的关系

- **当前主流程：GitHub + 自托管 Runner 自动部署**  
- Gitee 仓库可作备份（远程名常为 `gitee`）  
- 本机默认 `git push` 推 GitHub（`origin`）
