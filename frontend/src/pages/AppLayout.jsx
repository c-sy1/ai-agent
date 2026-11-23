import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { getSession } from "../api";

export default function AppLayout() {
  const user = getSession();
  const navigate = useNavigate();
  // 登录账号用 username；昵称仅作展示名。两者不同时都显示，避免对不上。
  const username = user?.username || "用户";
  const nickname = (user?.nickname || "").trim();
  const displayName = nickname || username;
  const showLoginName = Boolean(nickname && nickname !== username);

  const newChat = () => navigate("/chat");

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <NavLink to="/" className="brand">
          <div className="brand-icon">🤖</div>
          Apex AI
        </NavLink>
        <button type="button" className="btn-primary" onClick={newChat}>
          + 新建对话
        </button>
        <nav className="nav-list">
          <NavLink to="/toolbox" className={({ isActive }) => `nav-item${isActive ? " active" : ""}`}>
            🧰 工具箱
          </NavLink>
          <NavLink to="/agents" className={({ isActive }) => `nav-item${isActive ? " active" : ""}`}>
            🤖 智能体
          </NavLink>
          <div className="nav-sub">智能体广场</div>
          <NavLink
            to="/chat"
            className={({ isActive }) => `nav-item nav-sub${isActive ? " active" : ""}`}
          >
            网页版对话记录
          </NavLink>
          {user?.is_admin ? (
            <NavLink to="/admin" className={({ isActive }) => `nav-item${isActive ? " active" : ""}`}>
              🛠 管理后台
            </NavLink>
          ) : null}
          <span className="nav-item nav-sub" style={{ opacity: 0.5 }}>
            APP 对话记录
          </span>
        </nav>
        <NavLink
          to="/profile"
          className={({ isActive }) => `user-bar user-bar-link${isActive ? " active" : ""}`}
          title="进入个人主页"
        >
          <div className="avatar">{displayName.slice(0, 1)}</div>
          <div className="user-meta">
            <span className="user-display">{displayName}</span>
            {showLoginName ? (
              <span className="user-login">@{username}</span>
            ) : (
              <span className="user-login">个人主页</span>
            )}
          </div>
        </NavLink>
      </aside>
      <div className="main-area">
        <Outlet />
      </div>
    </div>
  );
}
