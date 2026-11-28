import { useEffect, useMemo, useState } from "react";
import { api } from "../api";

const STATUS_OPTS = [
  { value: "pending", label: "待处理" },
  { value: "processing", label: "处理中" },
  { value: "resolved", label: "已解决" },
  { value: "closed", label: "已关闭" },
];

function statusLabel(v) {
  return STATUS_OPTS.find((x) => x.value === v)?.label || v || "待处理";
}

function formatTime(iso) {
  if (!iso) return "—";
  return String(iso).replace("T", " ").slice(0, 16);
}

export default function SupportAdmin() {
  const [rows, setRows] = useState([]);
  const [grantable, setGrantable] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [okMsg, setOkMsg] = useState("");
  const [statusFilter, setStatusFilter] = useState("pending");
  const [q, setQ] = useState("");
  const [active, setActive] = useState(null);
  const [reply, setReply] = useState("");
  const [status, setStatus] = useState("processing");
  const [grantCoupon, setGrantCoupon] = useState("");
  const [saving, setSaving] = useState(false);

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const r = await api.adminSupportTickets(statusFilter === "all" ? "" : statusFilter);
      setRows(r.data?.tickets || []);
      setGrantable(r.data?.grantable_coupons || []);
    } catch (e) {
      setError(e.message || "加载失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, [statusFilter]);

  const filtered = useMemo(() => {
    const key = q.trim().toLowerCase();
    if (!key) return rows;
    return rows.filter((t) => {
      const blob = `${t.id} ${t.username} ${t.nickname} ${t.title} ${t.content}`.toLowerCase();
      return blob.includes(key);
    });
  }, [rows, q]);

  const openTicket = (t) => {
    setActive(t);
    setReply(t.admin_reply || "");
    setStatus(t.status === "pending" ? "processing" : t.status || "processing");
    setGrantCoupon("");
    setOkMsg("");
    setError("");
  };

  const submit = async () => {
    if (!active) return;
    setSaving(true);
    setError("");
    setOkMsg("");
    try {
      const res = await api.adminSupportUpdate(active.id, {
        status,
        admin_reply: reply,
        grant_coupon: grantCoupon || null,
      });
      setOkMsg(res.msg || "已更新");
      setActive(res.data);
      await load();
    } catch (e) {
      setError(e.message || "更新失败");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="admin-page">
      <div className="admin-card">
        <div className="admin-card-head">
          <div>
            <h2>客服工单</h2>
            <p className="admin-muted">处理用户反馈，可回复并赠送补偿优惠券结案</p>
          </div>
          <button type="button" className="logout-btn" onClick={load} disabled={loading}>
            {loading ? "刷新中…" : "刷新"}
          </button>
        </div>

        <div className="admin-toolbar">
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="搜索用户名 / 工单内容"
          />
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
            <option value="all">全部状态</option>
            {STATUS_OPTS.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
        </div>

        {error ? <div className="form-error">{error}</div> : null}
        {okMsg ? <div className="form-ok">{okMsg}</div> : null}

        <div className="support-admin-grid">
          <div className="support-admin-list">
            {loading ? (
              <p className="admin-muted">加载中…</p>
            ) : filtered.length === 0 ? (
              <p className="admin-muted">暂无工单</p>
            ) : (
              <table className="admin-table">
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>用户</th>
                    <th>类型</th>
                    <th>标题</th>
                    <th>状态</th>
                    <th>时间</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((t) => (
                    <tr
                      key={t.id}
                      className={active?.id === t.id ? "on" : ""}
                      onClick={() => openTicket(t)}
                      style={{ cursor: "pointer" }}
                    >
                      <td>#{t.id}</td>
                      <td>{t.nickname || t.username}</td>
                      <td>{t.category_label}</td>
                      <td>{t.title}</td>
                      <td>
                        <span className={`order-status status-${t.status === "resolved" ? "paid" : t.status === "pending" ? "pending" : "cancelled"}`}>
                          {statusLabel(t.status)}
                        </span>
                      </td>
                      <td>{formatTime(t.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          <div className="support-admin-detail card">
            {!active ? (
              <p className="admin-muted">选择左侧工单进行处理</p>
            ) : (
              <>
                <h3>
                  #{active.id} · {active.title}
                </h3>
                <p className="admin-muted">
                  {active.nickname || active.username}（uid {active.user_id}）· {active.category_label} ·{" "}
                  {formatTime(active.created_at)}
                </p>
                <div className="support-user-content">{active.content}</div>

                <label className="form-field">
                  处理状态
                  <select value={status} onChange={(e) => setStatus(e.target.value)}>
                    {STATUS_OPTS.map((s) => (
                      <option key={s.value} value={s.value}>
                        {s.label}
                      </option>
                    ))}
                  </select>
                </label>

                <label className="form-field">
                  回复用户
                  <textarea
                    rows={4}
                    value={reply}
                    onChange={(e) => setReply(e.target.value)}
                    placeholder="说明处理结果、排查结论等"
                  />
                </label>

                <label className="form-field">
                  赠送补偿券（可选）
                  <select value={grantCoupon} onChange={(e) => setGrantCoupon(e.target.value)}>
                    <option value="">不赠券</option>
                    {grantable.map((c) => (
                      <option key={c.code} value={c.code}>
                        {c.label}（满 {c.min_amount} 减 {c.off}）
                      </option>
                    ))}
                  </select>
                </label>

                {active.granted_coupon_code ? (
                  <p className="form-ok">已赠券：{active.granted_coupon_code}</p>
                ) : null}
                {active.admin_reply ? (
                  <p className="admin-muted">当前回复：{active.admin_reply}</p>
                ) : null}

                <button type="button" className="btn-primary" disabled={saving} onClick={submit}>
                  {saving ? "提交中…" : grantCoupon ? "回复并赠券结案" : "提交处理"}
                </button>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
