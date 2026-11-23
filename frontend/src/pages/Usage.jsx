import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, getSession } from "../api";

export default function Usage() {
  const session = getSession();
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!session?.user_id) return;
    setLoading(true);
    api
      .profile(session.user_id)
      .then((r) => {
        setData(r.data);
        setError("");
      })
      .catch((e) => setError(e.message || "加载失败"))
      .finally(() => setLoading(false));
  }, [session?.user_id]);

  const usage = data?.usage;
  const chat = usage?.chat;
  const image = usage?.image;

  return (
    <div className="page-scroll">
      <div className="hero">
        <h1>今日用量</h1>
        <p className="profile-desc">
          {data?.is_vip ? "VIP 高额度" : "免费有日限，用完可开通 VIP"}
        </p>
      </div>

      {loading && <p className="profile-desc">加载中…</p>}
      {error && <p className="form-error">{error}</p>}

      {!loading && usage && (
        <div className="usage-page-grid">
          <div className="card usage-page-card">
            <h3>{chat?.label || "AI 对话"}</h3>
            <p className="usage-big">
              {chat?.used ?? 0}
              <span> / {chat?.unlimited ? "不限" : chat?.limit ?? 0}</span>
            </p>
            <p className="profile-desc">
              {chat?.unlimited ? "VIP 高额度" : `剩余 ${chat?.remain ?? 0} 次`}
            </p>
          </div>
          <div className="card usage-page-card">
            <h3>{image?.label || "AI 生图"}</h3>
            <p className="usage-big">
              {image?.used ?? 0}
              <span> / {image?.unlimited ? "不限" : image?.limit ?? 0}</span>
            </p>
            <p className="profile-desc">
              {image?.unlimited ? "VIP 高额度" : `剩余 ${image?.remain ?? 0} 次`}
            </p>
          </div>
        </div>
      )}

      <div style={{ marginTop: 24 }}>
        <Link to="/profile" className="btn-primary" style={{ display: "inline-block" }}>
          去开通 / 管理 VIP
        </Link>
      </div>
    </div>
  );
}
