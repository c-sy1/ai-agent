# Apex AI 智能体原型

前后端分离的 Apex AI 演示项目：登录/注册、首页、工具箱、智能体广场、对话记录（数据来自数据库）。

## 快速启动

首次安装：

```bash
cd backend
copy .env.example .env
pip install -r requirements.txt
python seed.py
cd ../frontend
npm install
```

### 方式 A：一键同端口（推荐）

双击 **`start.bat`**，或：

```bash
cd frontend && npm run build
cd ../backend && python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

浏览器打开 **http://127.0.0.1:8000**（页面 + `/api` 都在 8000，已连通）。

### 方式 B：开发双端口

双击 **`dev.bat`**，或手动开两个终端：

- 后端：`cd backend && uvicorn main:app --port 8000 --reload`
- 前端：`cd frontend && npm run dev`

浏览器打开 **http://127.0.0.1:5173**，`vite.config.js` 已将 `/api` 代理到 8000。

默认使用 SQLite 文件 `backend/apex_ai.db`。MySQL 配置见 `backend/.env.example`。

### 演示账号

- 用户名：`xiaoyema`
- 密码：`123456`

## 功能对照

| 界面 | 路由 | 接口 |
|------|------|------|
| 登录/注册 | `/login` | `POST /api/register`, `POST /api/login` |
| 首页（热搜/工具/智能体） | `/` | `GET /api/hot-topics`, tools, agents |
| 工具箱 | `/toolbox` | `GET /api/tools` |
| 智能体广场 | `/agents` | `GET /api/agents` |
| 网页版对话 | `/chat` | `GET /api/conversations`, `POST /api/chat` |

可选：在 `backend/.env` 配置 `QIANWEN_API_KEY` 后，对话将调用兼容 OpenAI 的大模型接口。
