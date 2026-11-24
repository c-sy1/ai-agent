import { useEffect, useState } from "react";
import { api } from "../api";

const CATS = ["全部", "红色文化", "景点介绍", "历史人文"];

export default function Knowledge() {
  const [category, setCategory] = useState("全部");
  const [docs, setDocs] = useState([]);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [newCat, setNewCat] = useState("景点介绍");
  const [error, setError] = useState("");
  const [ok, setOk] = useState("");
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const res = await api.knowledgeDocs(category === "全部" ? "" : category);
      setDocs(res.data || []);
    } catch (e) {
      setError(e.message || "加载失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, [category]);

  const create = async () => {
    setError("");
    setOk("");
    try {
      await api.knowledgeCreate({
        title: title.trim(),
        content: content.trim(),
        category: newCat,
      });
      setTitle("");
      setContent("");
      setOk("已入库");
      load();
    } catch (e) {
      setError(e.message || "保存失败");
    }
  };

  const remove = async (id) => {
    if (!window.confirm("确定删除该文档？")) return;
    try {
      await api.knowledgeRemove(id);
      load();
    } catch (e) {
      setError(e.message || "删除失败");
    }
  };

  return (
    <div className="page-scroll">
      <div className="hero">
        <h1>文旅知识库</h1>
        <p style={{ color: "#636e72", marginTop: 8 }}>
          按分类管理资料；对话时会自动检索相关文档辅助回答。
        </p>
      </div>

      <div className="card profile-form" style={{ marginBottom: 16 }}>
        <h2 className="panel-title">上传文档</h2>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 8 }}>
          <select value={newCat} onChange={(e) => setNewCat(e.target.value)}>
            {CATS.filter((c) => c !== "全部").map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
          <input
            style={{ flex: 1, minWidth: 160 }}
            placeholder="标题"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
        </div>
        <textarea
          rows={5}
          placeholder="粘贴景点介绍、红色故事、历史人文等内容…"
          value={content}
          onChange={(e) => setContent(e.target.value)}
          style={{ width: "100%", marginBottom: 8 }}
        />
        <button type="button" className="btn-primary" onClick={create}>
          保存到知识库
        </button>
        {ok && <p style={{ color: "#0b6e4f" }}>{ok}</p>}
        {error && <p style={{ color: "#c0392b" }}>{error}</p>}
      </div>

      <div style={{ display: "flex", gap: 8, marginBottom: 12, flexWrap: "wrap" }}>
        {CATS.map((c) => (
          <button
            key={c}
            type="button"
            className={`chip${category === c ? " active" : ""}`}
            onClick={() => setCategory(c)}
          >
            {c}
          </button>
        ))}
      </div>

      {loading && <p style={{ color: "#636e72" }}>加载中…</p>}
      <div className="tool-grid-sm">
        {docs.map((d) => (
          <div key={d.id} className="card tool-sm-card">
            <div>
              <span className="chip">{d.category}</span>
              <strong style={{ display: "block", marginTop: 8 }}>{d.title}</strong>
              <p style={{ margin: "8px 0", fontSize: 13, color: "#636e72", whiteSpace: "pre-wrap" }}>
                {d.content.slice(0, 180)}
                {d.content.length > 180 ? "…" : ""}
              </p>
              <button type="button" className="logout-btn" onClick={() => remove(d.id)}>
                删除
              </button>
            </div>
          </div>
        ))}
      </div>
      {!loading && docs.length === 0 && <p style={{ color: "#636e72" }}>该分类暂无文档</p>}
    </div>
  );
}
