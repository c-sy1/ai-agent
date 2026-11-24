import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { clearSession, getSession } from "../api";
import AdminMfaGate from "./AdminMfaGate";

export default function AdminLayout() {
  const user = getSession();
  const navigate = useNavigate();
  const name = user?.nickname || user?.username || "管理员";

  const logout = () => {
    clearSession();
    navigate("/admin/login", { replace: true });
  };

  return (
    <div className="admin-shell">
      <header className="admin-topbar">
        <div className="admin-topbar-brand">Apex AI · 管理后台</div>
        <nav className="admin-topbar-nav">
          <NavLink to="/admin" end className={({ isActive }) => (isActive ? "on" : "")}>
            用户与 VIP
          </NavLink>
          <NavLink to="/admin/feedback" className={({ isActive }) => (isActive ? "on" : "")}>
            对话反馈
          </NavLink>
          <NavLink to="/admin/knowledge" className={({ isActive }) => (isActive ? "on" : "")}>
            知识库维护
          </NavLink>
        </nav>
        <div className="admin-topbar-actions">
          <span className="admin-user-label">
            <span className="admin-role-badge">管理员</span>
            {name}
          </span>
          <button type="button" className="logout-btn" onClick={logout}>
            退出管理端
          </button>
        </div>
      </header>
      <div className="admin-body">
        <AdminMfaGate>
          <Outlet />
        </AdminMfaGate>
      </div>
    </div>
  );
}
