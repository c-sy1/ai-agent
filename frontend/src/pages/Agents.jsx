import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api, getSession } from "../api";

const CATEGORIES = [
  "全部分类",
  "效率工具",
  "学习教育",
  "职场攻略",
  "绘画",
  "写作",
  "生活实用",
];

export default function Agents() {
  const [all, setAll] = useState([]);
  const [category, setCategory] = useState("全部分类");
  const [q, setQ] = useState("");
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const user = getSession();

  useEffect(() => {
    api.agents().then((r) => setAll(r.data));
  }, []);

  useEffect(() => {
    const tryId = params.get("try");
    if (tryId && user) {
      api
        .createConversation({
          user_id: user.user_id,
          title: "智能体体验",
          agent_id: Number(tryId),
        })
        .then((r) => navigate(`/chat/${r.data.id}`));
    }
  }, [params, user, navigate]);

  const filtered = useMemo(() => {
    let list = all;
    if (category !== "全部分类") list = list.filter((a) => a.category === category);
    if (q.trim()) {
      const k = q.trim().toLowerCase();
      list = list.filter(
        (a) => a.name.toLowerCase().includes(k) || a.description.toLowerCase().includes(k)
      );
    }
    return list.filter((a) => !a.name.includes("时尚") && !a.name.includes("汽车"));
  }, [all, category, q]);

  const tryAgent = async (agentId) => {
    if (!user) return;
    const res = await api.createConversation({
      user_id: user.user_id,
      agent_id: agentId,
      title: "智能体对话",
    });
    navigate(`/chat/${res.data.id}`);
  };

  return (
    <div className="page-scroll">
      <h1 style={{ marginTop: 0 }}>发现</h1>
      <div className="banner-discover card">
        <div>
          <h2 style={{ margin: "0 0 8px" }}>想法无限可能</h2>
          <p style={{ margin: 0, color: "#636e72" }}>这里有你的最佳伙伴</p>
        </div>
        <button type="button" className="btn-primary">
          + 创建你的智能体
        </button>
      </div>

      <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginBottom: 16 }}>
        <div className="category-tabs" style={{ flex: 1, marginBottom: 0 }}>
          {CATEGORIES.map((c) => (
            <button
              key={c}
              type="button"
              className={`tab${category === c ? " active" : ""}`}
              onClick={() => setCategory(c)}
            >
              {c}
            </button>
          ))}
        </div>
        <div className="search-bar" style={{ margin: 0, maxWidth: 220 }}>
          <span>🔍</span>
          <input placeholder="搜索" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
      </div>

      <div className="agent-grid">
        {filtered.map((a) => (
          <div key={a.id} className="card agent-card">
            <div style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
              <span style={{ fontSize: 32 }}>{a.icon}</span>
              <div>
                <h3>{a.name}</h3>
                <div className="agent-meta">
                  <div className="avatar" style={{ width: 22, height: 22, fontSize: 10 }}>
                    宇
                  </div>
                  {a.author}
                </div>
              </div>
            </div>
            <p style={{ fontSize: 13, color: "#636e72", lineHeight: 1.6 }}>{a.description}</p>
            <div className="agent-stats">
              <span>
                ❤️ {a.likes} &nbsp; 🔥 {a.heat}
              </span>
              <button type="button" className="link-action" onClick={() => tryAgent(a.id)}>
                立即试用
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
