import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { clearSession, getSession } from "../api";

export default function AppLayout() {
  const user = getSession();
  const navigate = useNavigate();
  const username = user?.username || "用户";
  const nickname = (user?.nickname || "").trim();
  const displayName = nickname || username;
  const showLoginName = Boolean(nickname && nickname !== username);

  const newChat = () => navigate("/chat");
  const logout = () => {
    clearSession();
    navigate("/login", { replace: true });
  };

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
          <NavLink to="/map" className={({ isActive }) => `nav-item${isActive ? " active" : ""}`}>
            🗺️ 地图
          </NavLink>
          <NavLink
            to="/knowledge"
            className={({ isActive }) => `nav-item${isActive ? " active" : ""}`}
          >
            📚 知识库
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
        <button type="button" className="logout-btn" style={{ margin: "8px 12px 16px" }} onClick={logout}>
          退出登录
        </button>
      </aside>
      <div className="main-area">
        <Outlet />
      </div>
    </div>
  );
}
