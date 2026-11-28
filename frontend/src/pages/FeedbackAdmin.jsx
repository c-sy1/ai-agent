import { useEffect, useMemo, useState } from "react";
import { api, getSession } from "../api";

const PAGE_SIZE = 10;

const ISSUE_TAGS = [
  { value: "", label: "未分类" },
  { value: "hallucination", label: "回答幻觉" },
  { value: "kb_missing", label: "知识库缺失" },
  { value: "bug", label: "功能 bug" },
  { value: "other", label: "其他" },
];

const STATUS_OPTS = [
  { value: "pending", label: "待处理" },
  { value: "processing", label: "处理中" },
  { value: "resolved", label: "已解决" },
];

function previewContent(text) {
  return (text || "")
    .replace(/\[\[map:[^\]]+\]\]/g, "")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 120);
}

function formatTime(iso) {
  if (!iso) return "—";
  return String(iso).replace("T", " ").slice(0, 16);
}

function dayKey(iso) {
  if (!iso) return "";
  return String(iso).slice(0, 10);
}

function csvEscape(v) {
  const s = String(v ?? "");
  if (/[",\n]/.test(s)) return `"${s.replace(/"/g, '""')}"`;
  return s;
}

function downloadCsv(filename, rows) {
  const bom = "\uFEFF";
  const text = bom + rows.map((r) => r.map(csvEscape).join(",")).join("\n");
  const blob = new Blob([text], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function statusLabel(v) {
  return STATUS_OPTS.find((x) => x.value === v)?.label || v || "待处理";
}

function tagLabel(v) {
  return ISSUE_TAGS.find((x) => x.value === v)?.label || "未分类";
}

export default function FeedbackAdmin() {
  const session = getSession();
  const [rows, setRows] = useState([]);
  const [error, setError] = useState("");
  const [okMsg, setOkMsg] = useState("");
  const [loading, setLoading] = useState(true);
  const [ratingFilter, setRatingFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [q, setQ] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [selected, setSelected] = useState(() => new Set());
  const [page, setPage] = useState(1);
  const [editingId, setEditingId] = useState(null);
  const [editingComment, setEditingComment] = useState("");
  const [savingId, setSavingId] = useState(null);
  const [drawer, setDrawer] = useState(null);
  const [drawerMsgs, setDrawerMsgs] = useState([]);
  const [drawerLoading, setDrawerLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const r = await api.adminFeedback();
      setRows(r.data || []);
    } catch (e) {
      setError(e.message || "加载失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, [session?.user_id]);

  useEffect(() => {
    setPage(1);
    setSelected(new Set());
  }, [q, dateFrom, dateTo, ratingFilter, statusFilter]);

  const upCount = rows.filter((r) => r.rating === "up").length;
  const downCount = rows.filter((r) => r.rating === "down").length;
  const pendingCount = rows.filter((r) => (r.handle_status || "pending") === "pending").length;

  const filtered = useMemo(() => {
    const keyword = q.trim().toLowerCase();
    return rows.filter((r) => {
      if (ratingFilter === "up" && r.rating !== "up") return false;
      if (ratingFilter === "down" && r.rating !== "down") return false;
      if (statusFilter !== "all" && (r.handle_status || "pending") !== statusFilter) return false;
      const day = dayKey(r.created_at);
      if (dateFrom && day && day < dateFrom) return false;
      if (dateTo && day && day > dateTo) return false;
      if (keyword) {
        const hay = `${r.user_id} ${r.username || ""} ${r.nickname || ""}`.toLowerCase();
        if (!hay.includes(keyword)) return false;
      }
      return true;
    });
  }, [rows, q, dateFrom, dateTo, ratingFilter, statusFilter]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const pageRows = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
  const pageIds = pageRows.map((r) => r.id);
  const allPageSelected = pageIds.length > 0 && pageIds.every((id) => selected.has(id));

  const toggleOne = (id) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const togglePage = () => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (allPageSelected) pageIds.forEach((id) => next.delete(id));
      else pageIds.forEach((id) => next.add(id));
      return next;
    });
  };

  const patchRow = (id, patch) => {
    setRows((list) => list.map((r) => (r.id === id ? { ...r, ...patch } : r)));
  };

  const updateField = async (id, body) => {
    setSavingId(id);
    setError("");
    setOkMsg("");
    try {
      const res = await api.adminFeedbackUpdate(id, body);
      patchRow(id, res.data || body);
      setOkMsg("已保存");
    } catch (e) {
      setError(e.message || "保存失败");
      await load();
    } finally {
      setSavingId(null);
    }
  };

  const saveComment = async (id) => {
    await updateField(id, { comment: editingComment });
    setEditingId(null);
  };

  const batchStatus = async (handle_status) => {
    const ids = [...selected];
    if (!ids.length) return;
    setError("");
    setOkMsg("");
    try {
      const res = await api.adminFeedbackBatch({ ids, handle_status });
      setRows((list) =>
        list.map((r) => (ids.includes(r.id) ? { ...r, handle_status } : r))
      );
      setSelected(new Set());
      setOkMsg(res.msg || `已更新 ${ids.length} 条`);
    } catch (e) {
      setError(e.message || "批量更新失败");
    }
  };

  const openDrawer = async (row, e) => {
    if (e?.target?.closest?.("input,select,textarea,button,.fb-note-edit")) return;
    setDrawer(row);
    setDrawerMsgs([]);
    setDrawerLoading(true);
    try {
      const res = await api.adminFeedbackContext(row.id);
      setDrawer(res.data?.feedback || row);
      setDrawerMsgs(res.data?.messages || []);
    } catch (err) {
      setError(err.message || "加载上下文失败");
    } finally {
      setDrawerLoading(false);
    }
  };

  const exportExcel = () => {
    downloadCsv("对话反馈.csv", [
      ["时间", "用户ID", "用户名", "评价", "处理状态", "问题标签", "回复摘要", "备注"],
      ...filtered.map((r) => [
        formatTime(r.created_at),
        r.user_id,
        r.username || "",
        r.rating === "up" ? "满意" : "不满意",
        statusLabel(r.handle_status || "pending"),
        tagLabel(r.issue_tag || ""),
        previewContent(r.content_preview),
        r.comment || "",
      ]),
    ]);
  };

  return (
    <div className="admin-vip-page admin-vip-page-wide">
      <header className="admin-vip-toolbar">
        <div className="admin-vip-heading">
          <h1 className="admin-vip-title">对话反馈</h1>
          <div className="admin-vip-stats">
            <span>
              全部 <b>{rows.length}</b>
            </span>
            <span>
              满意 <b>{upCount}</b>
            </span>
            <span className={downCount ? "warn" : ""}>
              不满意 <b>{downCount}</b>
            </span>
            <span className={pendingCount ? "warn" : ""}>
              待处理 <b>{pendingCount}</b>
            </span>
          </div>
        </div>
        <div className="admin-vip-controls">
          <button type="button" className="admin-btn admin-btn-ghost" onClick={exportExcel}>
            导出 Excel
          </button>
        </div>
      </header>

      <div className="admin-toolbar-row">
        <input
          className="admin-search"
          type="search"
          placeholder="搜索用户名 / ID"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <input
          className="admin-filter admin-date"
          type="date"
          value={dateFrom}
          onChange={(e) => setDateFrom(e.target.value)}
          title="开始日期"
        />
        <input
          className="admin-filter admin-date"
          type="date"
          value={dateTo}
          onChange={(e) => setDateTo(e.target.value)}
          title="结束日期"
        />
        <select className="admin-filter" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="all">全部状态</option>
          {STATUS_OPTS.map((s) => (
            <option key={s.value} value={s.value}>
              {s.label}
            </option>
          ))}
        </select>
        {selected.size > 0 ? (
          <>
            <button type="button" className="admin-btn admin-btn-ghost" onClick={() => batchStatus("processing")}>
              标为处理中（{selected.size}）
            </button>
            <button type="button" className="admin-btn admin-btn-primary" onClick={() => batchStatus("resolved")}>
              标为已解决（{selected.size}）
            </button>
          </>
        ) : null}
      </div>

      {error && <div className="form-error">{error}</div>}
      {okMsg && <div className="form-ok">{okMsg}</div>}

      <div className="admin-tabs" role="tablist">
        <button type="button" className={ratingFilter === "all" ? "on" : ""} onClick={() => setRatingFilter("all")}>
          全部
        </button>
        <button type="button" className={ratingFilter === "up" ? "on" : ""} onClick={() => setRatingFilter("up")}>
          满意
        </button>
        <button type="button" className={ratingFilter === "down" ? "on" : ""} onClick={() => setRatingFilter("down")}>
          不满意
        </button>
      </div>

      {loading ? (
        <p className="admin-vip-loading">加载中…</p>
      ) : (
        <>
          <div className="admin-panel">
            <table className="admin-table admin-table-feedback">
              <thead>
                <tr>
                  <th className="th-check">
                    <input type="checkbox" checked={allPageSelected} onChange={togglePage} aria-label="全选本页" />
                  </th>
                  <th>时间</th>
                  <th>用户</th>
                  <th>评价</th>
                  <th>处理状态</th>
                  <th>问题标签</th>
                  <th>回复摘要</th>
                  <th>备注</th>
                </tr>
              </thead>
              <tbody>
                {pageRows.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="admin-empty">
                      <div className="admin-empty-box">
                        <strong>暂无反馈</strong>
                        <span>试试调整搜索、时间或状态筛选</span>
                      </div>
                    </td>
                  </tr>
                ) : (
                  pageRows.map((r) => {
                    const preview = previewContent(r.content_preview);
                    const st = r.handle_status || "pending";
                    return (
                      <tr key={r.id} className="fb-row" onClick={(e) => openDrawer(r, e)}>
                        <td className="td-check" onClick={(e) => e.stopPropagation()}>
                          <input
                            type="checkbox"
                            checked={selected.has(r.id)}
                            onChange={() => toggleOne(r.id)}
                            aria-label={`选择反馈 ${r.id}`}
                          />
                        </td>
                        <td className="td-muted">{formatTime(r.created_at)}</td>
                        <td>
                          <div className="admin-user-cell">
                            <strong>{r.username || `用户 ${r.user_id}`}</strong>
                            <span>ID {r.user_id}</span>
                          </div>
                        </td>
                        <td>
                          <span className={`admin-pill ${r.rating === "up" ? "fb-up" : "fb-down"}`}>
                            {r.rating === "up" ? "满意" : "不满意"}
                          </span>
                        </td>
                        <td onClick={(e) => e.stopPropagation()}>
                          <select
                            className={`fb-select status-${st}`}
                            value={st}
                            disabled={savingId === r.id}
                            onChange={(e) => updateField(r.id, { handle_status: e.target.value })}
                          >
                            {STATUS_OPTS.map((s) => (
                              <option key={s.value} value={s.value}>
                                {s.label}
                              </option>
                            ))}
                          </select>
                        </td>
                        <td onClick={(e) => e.stopPropagation()}>
                          <select
                            className="fb-select"
                            value={r.issue_tag || ""}
                            disabled={savingId === r.id}
                            onChange={(e) => updateField(r.id, { issue_tag: e.target.value })}
                          >
                            {ISSUE_TAGS.map((t) => (
                              <option key={t.value || "none"} value={t.value}>
                                {t.label}
                              </option>
                            ))}
                          </select>
                        </td>
                        <td className="td-preview" title={preview}>
                          {preview || "—"}
                        </td>
                        <td className="fb-note-cell" onClick={(e) => e.stopPropagation()}>
                          {editingId === r.id ? (
                            <div className="fb-note-edit">
                              <input
                                value={editingComment}
                                onChange={(e) => setEditingComment(e.target.value)}
                                onKeyDown={(e) => {
                                  if (e.key === "Enter") saveComment(r.id);
                                  if (e.key === "Escape") setEditingId(null);
                                }}
                                autoFocus
                              />
                              <button
                                type="button"
                                className="admin-btn admin-btn-primary"
                                disabled={savingId === r.id}
                                onClick={() => saveComment(r.id)}
                              >
                                保存
                              </button>
                            </div>
                          ) : (
                            <button
                              type="button"
                              className="fb-note-btn"
                              onClick={() => {
                                setEditingId(r.id);
                                setEditingComment(r.comment || "");
                              }}
                            >
                              {r.comment || "点击添加备注"}
                            </button>
                          )}
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
          {filtered.length > 0 ? (
            <div className="admin-pager">
              <span>
                第 {page} / {totalPages} 页 · 共 {filtered.length} 条
              </span>
              <div className="admin-pager-btns">
                <button
                  type="button"
                  className="admin-btn admin-btn-ghost"
                  disabled={page <= 1}
                  onClick={() => setPage((p) => p - 1)}
                >
                  上一页
                </button>
                <button
                  type="button"
                  className="admin-btn admin-btn-ghost"
                  disabled={page >= totalPages}
                  onClick={() => setPage((p) => p + 1)}
                >
                  下一页
                </button>
              </div>
            </div>
          ) : null}
        </>
      )}

      {drawer ? (
        <div className="admin-drawer-mask" onClick={() => setDrawer(null)}>
          <aside className="admin-drawer admin-drawer-wide" onClick={(e) => e.stopPropagation()}>
            <header className="admin-drawer-head">
              <div>
                <h2>反馈详情</h2>
                <p>
                  {drawer.username || `用户 ${drawer.user_id}`} ·{" "}
                  {drawer.rating === "up" ? "满意" : "不满意"} · {formatTime(drawer.created_at)}
                </p>
              </div>
              <button type="button" className="admin-btn admin-btn-ghost" onClick={() => setDrawer(null)}>
                关闭
              </button>
            </header>
            <div className="admin-drawer-body">
              <div className="admin-drawer-meta">
                <span className={`admin-pill ${drawer.rating === "up" ? "fb-up" : "fb-down"}`}>
                  {drawer.rating === "up" ? "满意" : "不满意"}
                </span>
                <span className={`admin-pill status-badge fb-status-${drawer.handle_status || "pending"}`}>
                  {statusLabel(drawer.handle_status || "pending")}
                </span>
                <span className="admin-pill">{tagLabel(drawer.issue_tag || "")}</span>
              </div>
              <h3>完整对话上下文</h3>
              {drawerLoading ? (
                <p className="admin-vip-loading">加载中…</p>
              ) : drawerMsgs.length === 0 ? (
                <p className="admin-drawer-empty">暂无对话上下文</p>
              ) : (
                <ul className="fb-context-list">
                  {drawerMsgs.map((m) => (
                    <li key={m.id} className={`fb-context-msg ${m.role}${m.is_target ? " target" : ""}`}>
                      <strong>{m.role === "ai" ? "AI" : "用户"}</strong>
                      <p>{(m.content || "").replace(/\[\[map:[^\]]+\]\]/g, "[地图]")}</p>
                      <em>{formatTime(m.created_at)}</em>
                    </li>
                  ))}
                </ul>
              )}
              {drawer.comment ? (
                <>
                  <h3>备注</h3>
                  <p className="admin-drawer-empty" style={{ color: "#475569" }}>
                    {drawer.comment}
                  </p>
                </>
              ) : null}
            </div>
          </aside>
        </div>
      ) : null}
    </div>
  );
}
