import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { getSession } from "./api";
import Login from "./pages/Login";
import AppLayout from "./pages/AppLayout";
import Home from "./pages/Home";
import Toolbox from "./pages/Toolbox";
import Agents from "./pages/Agents";
import Chat from "./pages/Chat";
import Profile from "./pages/Profile";
import Works from "./pages/Works";
import Usage from "./pages/Usage";
import Admin from "./pages/Admin";
import AdminLayout from "./pages/AdminLayout";
import MapChat from "./pages/MapChat";
import Knowledge from "./pages/Knowledge";
import FeedbackAdmin from "./pages/FeedbackAdmin";
import SupportAdmin from "./pages/SupportAdmin";

/** 普通用户区：未登录去用户登录；管理员请走管理端 */
function RequireUser({ children }) {
  const session = getSession();
  const location = useLocation();
  if (!session) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }
  if (session.is_admin) {
    return <Navigate to="/admin" replace />;
  }
  return children;
}

/** 管理端：未登录去管理登录；非管理员踢回用户登录 */
function RequireAdmin({ children }) {
  const session = getSession();
  if (!session) {
    return <Navigate to="/admin/login" replace />;
  }
  if (!session.is_admin) {
    return <Navigate to="/login" replace />;
  }
  return children;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login portal="user" />} />
      <Route path="/admin/login" element={<Login portal="admin" />} />

      <Route
        path="/"
        element={
          <RequireUser>
            <AppLayout />
          </RequireUser>
        }
      >
        <Route index element={<Home />} />
        <Route path="toolbox" element={<Toolbox />} />
        <Route path="agents" element={<Agents />} />
        <Route path="chat" element={<Chat />} />
        <Route path="chat/:conversationId" element={<Chat />} />
        <Route path="map" element={<MapChat />} />
        <Route path="knowledge" element={<Knowledge manage={false} />} />
        <Route path="works" element={<Works />} />
        <Route path="usage" element={<Usage />} />
        <Route path="profile" element={<Profile />} />
      </Route>

      <Route
        path="/admin"
        element={
          <RequireAdmin>
            <AdminLayout />
          </RequireAdmin>
        }
      >
        <Route index element={<Admin />} />
        <Route path="feedback" element={<FeedbackAdmin />} />
        <Route path="support" element={<SupportAdmin />} />
        <Route path="knowledge" element={<Knowledge manage />} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
