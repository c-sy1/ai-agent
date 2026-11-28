import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";

const CATS = ["全部", "使用说明", "业务资料", "常见问题"];

const CAT_TONE = {
  使用说明: "tone-green",
  业务资料: "tone-amber",
  常见问题: "tone-red",
};

export default function Knowledge({ manage = false }) {
  const canManage = Boolean(manage);
  const [category, setCategory] = useState("全部");
  const [docs, setDocs] = useState([]);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [newCat, setNewCat] = useState("业务资料");
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

  if (canManage) {
    return (
      <div className="admin-vip-page admin-kb-page">
        <header className="admin-vip-toolbar">
          <div className="admin-vip-heading">
            <h1 className="admin-vip-title">知识库维护</h1>
            <div className="admin-vip-stats">
              <span>
                文档 <b>{docs.length}</b>
              </span>
              <span>
                分类 <b>{category}</b>
              </span>
            </div>
          </div>
        </header>

        <section className="admin-kb-composer">
          <div className="admin-kb-composer-top">
            <h2>新增资料</h2>
            <div className="admin-kb-cat-select">
              {CATS.filter((c) => c !== "全部").map((c) => (
                <button
                  key={c}
                  type="button"
                  className={`admin-kb-chip${newCat === c ? " on" : ""}`}
                  onClick={() => setNewCat(c)}
                >
                  {c}
                </button>
              ))}
            </div>
          </div>
          <input
            className="admin-kb-input"
            placeholder="标题，例如：VIP 套餐说明"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
          <textarea
            className="admin-kb-textarea"
            rows={4}
            placeholder="粘贴正文：使用说明、业务资料、常见问题…"
            value={content}
            onChange={(e) => setContent(e.target.value)}
          />
          <div className="admin-kb-composer-actions">
            <button
              type="button"
              className="admin-btn admin-btn-primary"
              disabled={saving || !title.trim() || !content.trim()}
              onClick={create}
            >
              {saving ? "保存中…" : "保存"}
            </button>
            {ok && <span className="kb-ok">{ok}</span>}
            {error && <span className="kb-err">{error}</span>}
          </div>
        </section>

        <div className="admin-tabs" role="tablist">
          {CATS.map((c) => (
            <button
              key={c}
              type="button"
              role="tab"
              className={category === c ? "on" : ""}
              onClick={() => setCategory(c)}
            >
              {c}
            </button>
          ))}
        </div>

        {loading ? (
          <p className="admin-vip-loading">加载中…</p>
        ) : docs.length === 0 ? (
          <div className="admin-panel">
            <p className="admin-empty">该分类暂无文档，上方可新增。</p>
          </div>
        ) : (
          <div className="admin-kb-list">
            {docs.map((d) => {
              const open = expanded === d.id;
              return (
                <article key={d.id} className={`admin-kb-item${open ? " open" : ""}`}>
                  <button
                    type="button"
                    className="admin-kb-item-main"
                    onClick={() => setExpanded(open ? null : d.id)}
                  >
                    <span className={`admin-pill kb-cat ${CAT_TONE[d.category] || ""}`}>
                      {d.category}
                    </span>
                    <div className="admin-kb-item-text">
                      <strong>{d.title}</strong>
                      <p>
                        {open
                          ? d.content
                          : `${d.content.slice(0, 100)}${d.content.length > 100 ? "…" : ""}`}
                      </p>
                    </div>
                    <span className="admin-kb-chevron">{open ? "收起" : "展开"}</span>
                  </button>
                  <button
                    type="button"
                    className="admin-btn admin-btn-ghost"
                    onClick={() => remove(d.id)}
                  >
                    删除
                  </button>
                </article>
              );
            })}
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="page-scroll kb-page">
      <header className="kb-header">
        <div>
          <p className="kb-eyebrow">Knowledge</p>
          <h1>知识库</h1>
          <p className="kb-lead">
            共享知识库仅供浏览；在 <Link to="/chat">对话</Link> 提问时会自动引用。
            资料由管理端维护。
          </p>
        </div>
        <div className="kb-stat">
          <strong>{docs.length}</strong>
          <span>{category === "全部" ? "篇文档" : "篇 · 当前分类"}</span>
        </div>
      </header>

      <p className="kb-muted" style={{ textAlign: "left", padding: "0 0 16px" }}>
        仅可查看；新增/删除请使用管理端（/admin/login）。
      </p>

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
              <button
                type="button"
                className="kb-item-main"
                onClick={() => setExpanded(open ? null : d.id)}
              >
                <span className={`kb-tag ${CAT_TONE[d.category] || ""}`}>{d.category}</span>
                <div className="kb-item-text">
                  <h3>{d.title}</h3>
                  <p>
                    {open
                      ? d.content
                      : `${d.content.slice(0, 90)}${d.content.length > 90 ? "…" : ""}`}
                  </p>
                </div>
                <span className="kb-chevron">{open ? "收起" : "展开"}</span>
              </button>
            </article>
          );
        })}
      </div>

      {!loading && docs.length === 0 && <p className="kb-muted">该分类暂无文档。</p>}
      {error && <p className="kb-err">{error}</p>}
    </div>
  );
}
