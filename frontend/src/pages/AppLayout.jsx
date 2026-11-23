import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { getSession } from "../api";

export default function AppLayout() {
  const user = getSession();
  const navigate = useNavigate();
  const username = user?.username || "用户";
  const nickname = (user?.nickname || "").trim();
  const displayName = nickname || username;
  const showLoginName = Boolean(nickname && nickname !== username);
  const isAdmin = Boolean(user?.is_admin);

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
          <div className="nav-group-label">发现</div>
          <NavLink to="/" end className={({ isActive }) => `nav-item${isActive ? " active" : ""}`}>
            🏠 首页
          </NavLink>
          <NavLink to="/toolbox" className={({ isActive }) => `nav-item${isActive ? " active" : ""}`}>
            🧰 工具箱
          </NavLink>
          <NavLink to="/agents" className={({ isActive }) => `nav-item${isActive ? " active" : ""}`}>
            🤖 智能体
          </NavLink>

          <div className="nav-group-label">创作</div>
          <NavLink to="/chat" className={({ isActive }) => `nav-item${isActive ? " active" : ""}`}>
            💬 对话记录
          </NavLink>
          <NavLink to="/works" className={({ isActive }) => `nav-item${isActive ? " active" : ""}`}>
            🖼️ 我的作品
          </NavLink>
          <NavLink
            to="/toolbox?q=照片"
            className={({ isActive }) => `nav-item${isActive ? " active" : ""}`}
          >
            ✨ 照片修复
          </NavLink>

          <div className="nav-group-label">会员</div>
          <NavLink to="/profile" className={({ isActive }) => `nav-item${isActive ? " active" : ""}`}>
            👑 会员中心
          </NavLink>
          <NavLink to="/usage" className={({ isActive }) => `nav-item${isActive ? " active" : ""}`}>
            📊 今日用量
          </NavLink>

          {isAdmin && (
            <>
              <div className="nav-group-label">运营</div>
              <NavLink to="/admin" className={({ isActive }) => `nav-item${isActive ? " active" : ""}`}>
                🛡️ 管理后台
              </NavLink>
            </>
          )}
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
