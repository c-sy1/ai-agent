import { useEffect, useState } from "react";
import { api } from "../api";

const CATS = ["全部", "红色文化", "景点介绍", "历史人文"];

const CAT_TONE = {
  红色文化: "tone-red",
  景点介绍: "tone-green",
  历史人文: "tone-amber",
};

export default function Knowledge() {
  const [category, setCategory] = useState("全部");
  const [docs, setDocs] = useState([]);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [newCat, setNewCat] = useState("景点介绍");
  const [error, setError] = useState("");
  const [ok, setOk] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [expanded, setExpanded] = useState(null);

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
    setSaving(true);
    try {
      await api.knowledgeCreate({
        title: title.trim(),
        content: content.trim(),
        category: newCat,
      });
      setTitle("");
      setContent("");
      setOk("已保存到知识库");
      load();
    } catch (e) {
      setError(e.message || "保存失败");
    } finally {
      setSaving(false);
    }
  };

  const remove = async (id) => {
    if (!window.confirm("确定删除该文档？")) return;
    try {
      await api.knowledgeRemove(id);
      if (expanded === id) setExpanded(null);
      load();
    } catch (e) {
      setError(e.message || "删除失败");
    }
  };

  return (
    <div className="page-scroll kb-page">
      <header className="kb-header">
        <div>
          <p className="kb-eyebrow">Culture & Tourism</p>
          <h1>文旅知识库</h1>
          <p className="kb-lead">
            这里存放保定文旅资料。你在「对话 / 地图」里问狼牙山、白洋淀、西大街等时，
            系统会自动检索本库，并在回答末尾标注「已参考文旅知识库」。
          </p>
        </div>
        <div className="kb-stat">
          <strong>{docs.length}</strong>
          <span>{category === "全部" ? "篇文档" : "篇 · 当前分类"}</span>
        </div>
      </header>

      <section className="kb-composer">
        <div className="kb-composer-top">
          <h2>新增资料</h2>
          <div className="kb-cat-select">
            {CATS.filter((c) => c !== "全部").map((c) => (
              <button
                key={c}
                type="button"
                className={`kb-mini-tab${newCat === c ? " on" : ""}`}
                onClick={() => setNewCat(c)}
              >
                {c}
              </button>
            ))}
          </div>
        </div>
        <input
          className="kb-input"
          placeholder="标题，例如：白洋淀游船须知"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
        />
        <textarea
          className="kb-textarea"
          rows={4}
          placeholder="粘贴正文：景点介绍、红色故事、历史人文…"
          value={content}
          onChange={(e) => setContent(e.target.value)}
        />
        <div className="kb-composer-actions">
          <button
            type="button"
            className="btn-primary"
            disabled={saving || !title.trim() || !content.trim()}
            onClick={create}
          >
            {saving ? "保存中…" : "保存"}
          </button>
          {ok && <span className="kb-ok">{ok}</span>}
          {error && <span className="kb-err">{error}</span>}
        </div>
      </section>

      <div className="kb-filter">
        {CATS.map((c) => (
          <button
            key={c}
            type="button"
            className={`kb-filter-btn${category === c ? " on" : ""}`}
            onClick={() => setCategory(c)}
          >
            {c}
          </button>
        ))}
      </div>

      {loading && <p className="kb-muted">加载中…</p>}

      <div className="kb-list">
        {docs.map((d) => {
          const open = expanded === d.id;
          return (
            <article key={d.id} className={`kb-item${open ? " open" : ""}`}>
              <button type="button" className="kb-item-main" onClick={() => setExpanded(open ? null : d.id)}>
                <span className={`kb-tag ${CAT_TONE[d.category] || ""}`}>{d.category}</span>
                <div className="kb-item-text">
                  <h3>{d.title}</h3>
                  <p>{open ? d.content : `${d.content.slice(0, 90)}${d.content.length > 90 ? "…" : ""}`}</p>
                </div>
                <span className="kb-chevron">{open ? "收起" : "展开"}</span>
              </button>
              <div className="kb-item-actions">
                <button type="button" className="kb-del" onClick={() => remove(d.id)}>
                  删除
                </button>
              </div>
            </article>
          );
        })}
      </div>

      {!loading && docs.length === 0 && <p className="kb-muted">该分类暂无文档，上方可新增。</p>}
    </div>
  );
}
