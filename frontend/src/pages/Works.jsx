import { useEffect, useState } from "react";
import { api, resolveAssetUrl } from "../api";

export default function Works() {
  const [items, setItems] = useState([]);
  const [kind, setKind] = useState("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = () => {
    setLoading(true);
    api
      .works({ kind })
      .then((r) => {
        setItems(r.data || []);
        setError("");
      })
      .catch((e) => setError(e.message || "加载失败"))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, [kind]);

  return (
    <div className="page-scroll">
      <div className="hero">
        <h1>我的作品</h1>
        <p className="profile-desc">生图、修图、视频结果集中在这里，可预览与下载。</p>
      </div>

      <div className="works-tabs">
        {[
          ["all", "全部"],
          ["image", "图片"],
          ["video", "视频"],
        ].map(([k, label]) => (
          <button
            key={k}
            type="button"
            className={kind === k ? "active" : ""}
            onClick={() => setKind(k)}
          >
            {label}
          </button>
        ))}
      </div>

      {loading && <p className="profile-desc">加载中…</p>}
      {error && <p className="form-error">{error}</p>}
      {!loading && !error && items.length === 0 && (
        <p className="profile-desc">暂无作品。去对话里生图/视频，或在工具箱修图后回来查看。</p>
      )}

      <div className="works-grid">
        {items.map((it) => (
          <article key={it.id} className="works-card">
            {it.kind === "video" ? (
              <video src={resolveAssetUrl(it.url)} controls preload="metadata" />
            ) : (
              <img src={resolveAssetUrl(it.url)} alt={it.name} loading="lazy" />
            )}
            <div className="works-meta">
              <span>{it.kind === "video" ? "视频" : "图片"}</span>
              <a href={resolveAssetUrl(it.url)} download={it.name} target="_blank" rel="noreferrer">
                下载
              </a>
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}
