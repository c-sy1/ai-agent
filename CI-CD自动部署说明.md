# Apex AI 项目 · CI/CD 自动部署说明

> **说的就是本项目（Apex AI）**，不是让你再新建一个仓库从头上传。  
> 代码、Runner、自动部署 **已经配好了**。你日常只需改代码后 push。

---

## 0. 本项目现在的状态（先看这里）

| 项目 | 已经好了吗 | 地址 / 位置 |
|------|------------|-------------|
| GitHub 仓库 | ✅ 已有 | https://github.com/c-sy1/ai-agent |
| 云服务器网站 | ✅ 已上线 | http://39.106.162.243:8000 |
| 服务器代码目录 | ✅ | `/opt/apex-ai` |
| 自动部署流水线 | ✅ | 仓库 → Actions |
| 自托管 Runner | ✅ | Settings → Actions → Runners |
| 后端自动拉起 | ✅ | systemd 服务名 `apex-ai` |

**所以：不用再 `git init`，不用再「第一次上传整个项目」。**

---

## 一、对本项目来说，CI/CD 有什么用？

你改完 Apex AI 的代码 → `git push` → 阿里云上的网站**自动变成新版本**。

不用每次打开 Workbench 手工拷文件、敲启动命令。答辩可以说：我们做了提交即发布的工程化流水线。

---

## 二、本项目自动部署怎么走？

```
你在本机改 Apex AI 代码
        ↓
git add . 
git commit -m "说明"
git push          ← 上传到 GitHub（更新，不是第一次建仓）
        ↓
GitHub 仓库：https://github.com/c-sy1/ai-agent
        ↓
Actions 工作流：Deploy to Aliyun ECS
        ↓
云主机上的 Runner 执行 deploy.sh
        ↓
/opt/apex-ai 更新 → 构建前端 → systemctl 重启 apex-ai
        ↓
打开 http://39.106.162.243:8000 看到新页面
```

---

## 三、你平时只敲这三条命令

在本机目录：

`C:\Users\lenovo\Desktop\项目总和\AI智能体原型`

```bash
git add .
git commit -m "说明这次改了什么"
git push
```

含义（针对本项目）：

| 命令 | 意思 |
|------|------|
| `git add .` | 把你改过的 Apex AI 文件选中 |
| `git commit -m "..."` | 在本机记下这一版 |
| `git push` | **把这一版更新上传到已有的 GitHub 仓库**，并触发自动部署 |

然后：

1. 看部署：https://github.com/c-sy1/ai-agent/actions  
2. 看网站：http://39.106.162.243:8000 （要带 `:8000`，Ctrl+F5 强刷）

若出现 `nothing to commit, working tree clean`：说明没有新改动，**不是取消**，只是没东西可提交。

---

## 四、本项目相关东西「在哪找」

| 要找什么 | 打开哪里 |
|----------|----------|
| 代码仓库 | https://github.com/c-sy1/ai-agent |
| 部署成功/失败 | https://github.com/c-sy1/ai-agent/actions |
| Runner 是否在线 | https://github.com/c-sy1/ai-agent/settings/actions/runners |
| 工作流文件 | 仓库里 `.github/workflows/deploy.yml` |
| 部署脚本 | 仓库根目录 `deploy.sh` |
| 后端服务配置 | `deploy/apex-ai.service` |
| 线上网站 | http://39.106.162.243:8000 |
| 本机项目 | `桌面\项目总和\AI智能体原型` |

---

## 五、本项目服务器上（一般不用动）

| 位置 | 说明 |
|------|------|
| `/opt/apex-ai` | 线上跑的代码 |
| `/home/admin/actions-runner` | GitHub Runner |
| `sudo systemctl status apex-ai` | 看后端是否在跑 |
| `sudo systemctl restart apex-ai` | 网站挂了可手动重启 |

---

## 六、答辩 30 秒（本项目）

「Apex AI 代码托管在 GitHub。向 master 推送后，GitHub Actions 触发部署；执行器是装在阿里云轻量服务器上的自托管 Runner，自动执行 deploy.sh：同步代码、构建前端、用 systemd 重启后端。公网地址可访问最新版本，Actions 页面可查看每次发布结果。」

---

## 七、和「第一次上传」的区别（避免再混淆）

| | 第一次建项目（已经做过） | 你现在日常（只用这个） |
|--|-------------------------|------------------------|
| 目的 | 把空仓库填满、服务器装好 | 更新已有网站 |
| 典型命令 | `git init`、新建 GitHub 仓、`clone` 到服务器、装 Runner | `git add` → `commit` → `push` |
| Apex AI | ✅ 已完成 | 改代码后 push 即可 |
