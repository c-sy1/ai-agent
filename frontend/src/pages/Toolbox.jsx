import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../api";
import ToolPanel from "../components/ToolPanel";

const OFFICIAL_GRADIENTS = [
  "linear-gradient(135deg,#fd79a8,#e84393)",
  "linear-gradient(135deg,#74b9ff,#0984e3)",
  "linear-gradient(135deg,#a29bfe,#6c5ce7)",
  "linear-gradient(135deg,#ffeaa7,#fdcb6e)",
];

function ToolCard({ tool, variant, gradient, onOpen }) {
  const clickable = { cursor: "pointer", transition: "transform 0.15s ease, box-shadow 0.15s ease" };
  const hoverProps = {
    onMouseEnter: (e) => {
      e.currentTarget.style.transform = "translateY(-2px)";
      e.currentTarget.style.boxShadow = "0 12px 28px rgba(108, 92, 231, 0.18)";
    },
    onMouseLeave: (e) => {
      e.currentTarget.style.transform = "";
      e.currentTarget.style.boxShadow = "";
    },
  };

  if (variant === "official") {
    return (
      <div
        role="button"
        tabIndex={0}
        className="official-card card"
        style={{ background: gradient, ...clickable }}
        onClick={() => onOpen(tool)}
        onKeyDown={(e) => e.key === "Enter" && onOpen(tool)}
        {...hoverProps}
      >
        <span style={{ fontSize: 32 }}>{tool.icon}</span>
        {tool.tag && (
          <span className="chip" style={{ display: "inline-block", marginTop: 8 }}>
            {tool.tag}
          </span>
        )}
        <h3>{tool.name}</h3>
        <p style={{ fontSize: 13, margin: "0 0 8px", opacity: 0.95 }}>{tool.description}</p>
        <span className="chip" style={{ background: "rgba(255,255,255,0.25)", border: "none" }}>
          点击使用 →
        </span>
      </div>
    );
  }

  return (
    <div
      role="button"
      tabIndex={0}
      className="card tool-sm-card"
      style={clickable}
      onClick={() => onOpen(tool)}
      onKeyDown={(e) => e.key === "Enter" && onOpen(tool)}
      {...hoverProps}
    >
      <span style={{ fontSize: 28 }}>{tool.icon}</span>
      <div>
        <strong>{tool.name}</strong>
        <p style={{ margin: "6px 0 0", fontSize: 13, color: "#636e72" }}>{tool.description}</p>
        <span style={{ fontSize: 12, color: "#6c5ce7", fontWeight: 600 }}>点击使用</span>
      </div>
    </div>
  );
}

export default function Toolbox() {
  const [searchParams] = useSearchParams();
  const [all, setAll] = useState([]);
  const [q, setQ] = useState(searchParams.get("q") || "");
  const [activeTool, setActiveTool] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fromUrl = searchParams.get("q");
    if (fromUrl != null) setQ(fromUrl);
  }, [searchParams]);

  useEffect(() => {
    setLoading(true);
    api
      .tools()
      .then((r) => {
        const list = r.data || [];
        setAll(list);
        setError("");
        // 侧边栏「照片修复」：自动打开匹配工具
        const keyword = (searchParams.get("q") || "").trim();
        if (keyword) {
          const hit = list.find(
            (t) =>
              (t.name || "").includes(keyword) ||
              (t.description || "").includes(keyword) ||
              (t.name || "").includes("修复") ||
              (t.name || "").includes("照片")
          );
          if (hit) setActiveTool(hit);
        }
      })
      .catch((e) => setError(e.message || "工具列表加载失败"))
      .finally(() => setLoading(false));
  }, [searchParams]);

  const filtered = useMemo(() => {
    if (!q.trim()) return all;
    const k = q.trim().toLowerCase();
    return all.filter(
      (t) => t.name.toLowerCase().includes(k) || t.description.toLowerCase().includes(k)
    );
  }, [all, q]);

  const official = filtered.filter((t) => t.category === "official");
  const office = filtered.filter((t) => t.category === "office");
  const life = filtered.filter((t) => t.category === "life");

  return (
    <>
      <div className="page-scroll">
        <div className="hero">
          <h1>你的全能智能外挂，点开即用！</h1>
        </div>
        <div className="search-bar">
          <span>🔍</span>
          <input
            placeholder="搜索工具名称"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>

        {loading && <p style={{ color: "#636e72" }}>工具加载中…</p>}
        {error && (
          <p style={{ color: "#c0392b", marginBottom: 16 }}>
            {error === "NETWORK" ? "后端未启动，请先启动服务后再刷新" : error}
          </p>
        )}
        {!loading && !error && filtered.length === 0 && (
          <p style={{ color: "#636e72", marginBottom: 16 }}>暂无工具数据</p>
        )}

        <h2 style={{ marginBottom: 16 }}>官方推荐</h2>
        <div className="tool-grid-official">
          {official.map((t, i) => (
            <ToolCard
              key={t.id}
              tool={t}
              variant="official"
              gradient={OFFICIAL_GRADIENTS[i % OFFICIAL_GRADIENTS.length]}
              onOpen={setActiveTool}
            />
          ))}
        </div>

        <h2 style={{ marginBottom: 16 }}>办公效率</h2>
        <div className="tool-grid-sm" style={{ marginBottom: 32 }}>
          {office.map((t) => (
            <ToolCard key={t.id} tool={t} onOpen={setActiveTool} />
          ))}
        </div>

        <h2 style={{ marginBottom: 16 }}>生活实用</h2>
        <div className="tool-grid-sm">
          {life.map((t) => (
            <ToolCard key={t.id} tool={t} onOpen={setActiveTool} />
          ))}
        </div>
      </div>

      <ToolPanel tool={activeTool} onClose={() => setActiveTool(null)} />
    </>
  );
}
