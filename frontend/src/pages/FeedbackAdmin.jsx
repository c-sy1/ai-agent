import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, getSession } from "../api";

export default function FeedbackAdmin() {
  const navigate = useNavigate();
  const session = getSession();
  const [rows, setRows] = useState([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!session?.user_id) {
      navigate("/login", { replace: true });
      return;
    }
    if (!session?.is_admin) {
      setError("需要管理员权限");
      setLoading(false);
      return;
    }
    api
      .adminFeedback()
      .then((r) => setRows(r.data || []))
      .catch((e) => setError(e.message || "加载失败"))
      .finally(() => setLoading(false));
  }, [session?.user_id]);

  return (
    <div className="page-scroll">
      <div className="hero">
        <h1>对话反馈管理</h1>
        <p style={{ color: "#636e72", marginTop: 8 }}>
          查看用户对 AI 回复的 👍 / 👎，用于迭代提示词与知识库。
        </p>
      </div>
      {loading && <p>加载中…</p>}
      {error && (
        <p style={{ color: "#c0392b" }}>
          {error} <Link to="/profile">返回</Link>
        </p>
      )}
      <div className="card" style={{ overflowX: "auto" }}>
        <table className="admin-table" style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              <th align="left">时间</th>
              <th align="left">用户</th>
              <th align="left">评价</th>
              <th align="left">回复摘要</th>
              <th align="left">备注</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td style={{ padding: "8px 6px", fontSize: 12 }}>{(r.created_at || "").slice(0, 19)}</td>
                <td style={{ padding: "8px 6px" }}>{r.username || r.user_id}</td>
                <td style={{ padding: "8px 6px" }}>{r.rating === "up" ? "👍 满意" : "👎 不满意"}</td>
                <td style={{ padding: "8px 6px", fontSize: 13, maxWidth: 360 }}>
                  {(r.content_preview || "").replace(/\[\[map:[^\]]+\]\]/g, "").slice(0, 120)}
                </td>
                <td style={{ padding: "8px 6px", fontSize: 12 }}>{r.comment || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!loading && !error && rows.length === 0 && (
          <p style={{ color: "#636e72", padding: 16 }}>暂无反馈</p>
        )}
      </div>
    </div>
  );
}
