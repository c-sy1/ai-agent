import { Navigate, Route, Routes } from "react-router-dom";
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
import MapChat from "./pages/MapChat";
import Knowledge from "./pages/Knowledge";
import FeedbackAdmin from "./pages/FeedbackAdmin";

function RequireAuth({ children }) {
  if (!getSession()) return <Navigate to="/login" replace />;
  return children;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        path="/"
        element={
          <RequireAuth>
            <AppLayout />
          </RequireAuth>
        }
      >
        <Route index element={<Home />} />
        <Route path="toolbox" element={<Toolbox />} />
        <Route path="agents" element={<Agents />} />
        <Route path="chat" element={<Chat />} />
        <Route path="chat/:conversationId" element={<Chat />} />
        <Route path="map" element={<MapChat />} />
        <Route path="knowledge" element={<Knowledge />} />
        <Route path="feedback-admin" element={<FeedbackAdmin />} />
        <Route path="works" element={<Works />} />
        <Route path="usage" element={<Usage />} />
        <Route path="profile" element={<Profile />} />
      </Route>
      <Route
        path="/admin"
        element={
          <RequireAuth>
            <Admin />
          </RequireAuth>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
