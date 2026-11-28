import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, getSession } from "../api";

const PAGE_SIZE = 10;

function shortTradeNo(no) {
  if (!no) return "—";
  if (no.length <= 14) return no;
  return `${no.slice(0, 8)}…${no.slice(-4)}`;
}

function statusLabel(status) {
  if (status === "paid") return "已支付";
  if (status === "pending") return "待支付";
  if (status === "cancelled") return "已取消";
  if (status === "closed") return "已关闭";
  return status || "—";
}

function channelLabel(channel) {
  if (channel === "alipay") return "支付宝";
  if (channel === "wechat") return "微信";
  if (channel === "admin") return "管理员";
  return channel || "—";
}

function actionLabel(action) {
  const map = {
    grant_vip: "开通 VIP",
    batch_grant_vip: "批量开通",
    batch_grant_vip_summary: "批量开通汇总",
    revoke_vip: "取消 VIP",
    approve_order: "审核订单",
  };
  return map[action] || action || "—";
}

function parseExpire(iso) {
  if (!iso) return null;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : d;
}

/** 到期栏展示：非 VIP 一律「—」；VIP ≤7 天或已过期标红；>7 天黑色 + tooltip */
function expireMeta(iso, isVip) {
  if (!isVip) {
    return { text: "—", className: "td-expire", tip: "" };
  }
  const d = parseExpire(iso);
  if (!d) {
    return { text: "—", className: "td-expire", tip: "暂无到期时间" };
  }
  const ms = d.getTime() - Date.now();
  const dayMs = 24 * 60 * 60 * 1000;
  const text = formatDate(iso);
  if (ms < 0) {
    const overdue = Math.max(1, Math.ceil(-ms / dayMs));
    return {
      text,
      className: "td-expire expire-alert",
      tip: `已过期 ${overdue} 天`,
    };
  }
  const daysLeft = Math.max(0, Math.ceil(ms / dayMs));
  if (daysLeft <= 7) {
    return {
      text,
      className: "td-expire expire-alert",
      tip: daysLeft === 0 ? "今天到期" : `剩余 ${daysLeft} 天，即将到期`,
    };
  }
  return {
    text,
    className: "td-expire expire-ok",
    tip: `剩余 ${daysLeft} 天`,
  };
}

function formatDate(iso, withTime = false) {
  if (!iso) return "—";
  const s = String(iso).replace("T", " ");
  return withTime ? s.slice(0, 16) : s.slice(0, 10);
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

function ConfirmModal({ open, title, message, confirmText = "确定", danger, busy, onConfirm, onCancel }) {
  if (!open) return null;
  return (
    <div className="admin-modal-mask" role="dialog" aria-modal="true">
      <div className="admin-modal">
        <h3>{title}</h3>
        <p>{message}</p>
        <div className="admin-modal-actions">
          <button type="button" className="admin-btn admin-btn-ghost" disabled={busy} onClick={onCancel}>
            取消
          </button>
          <button
            type="button"
            className={`admin-btn ${danger ? "admin-btn-danger" : "admin-btn-primary"}`}
            disabled={busy}
            onClick={onConfirm}
          >
            {busy ? "处理中…" : confirmText}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function Admin() {
  const navigate = useNavigate();
  const session = getSession();
  const [users, setUsers] = useState([]);
  const [orders, setOrders] = useState([]);
  const [logs, setLogs] = useState([]);
  const [packages, setPackages] = useState([]);
  const [packageId, setPackageId] = useState("vip_month");
  const [customDays, setCustomDays] = useState(30);
  const [tab, setTab] = useState("users");
  const [error, setError] = useState("");
  const [okMsg, setOkMsg] = useState("");
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");
  const [vipFilter, setVipFilter] = useState("all");
  const [orderFilter, setOrderFilter] = useState("all");
  const [selected, setSelected] = useState(() => new Set());
  const [page, setPage] = useState(1);
  const [orderPage, setOrderPage] = useState(1);
  const [logPage, setLogPage] = useState(1);
  const [confirm, setConfirm] = useState(null);
  const [busy, setBusy] = useState(false);
  const [drawerUser, setDrawerUser] = useState(null);
  const [drawerData, setDrawerData] = useState(null);
  const [drawerLoading, setDrawerLoading] = useState(false);

  const selectedPackage = packages.find((p) => p.id === packageId);
  const grantDays =
    packageId === "custom" ? Math.max(1, Number(customDays) || 30) : selectedPackage?.days || 30;
  const grantLabel =
    packageId === "custom"
      ? `自定义 ${grantDays} 天`
      : selectedPackage
        ? `${selectedPackage.name}（${selectedPackage.days} 天）`
        : `${grantDays} 天`;

  const load = async () => {
    if (!session?.user_id) return;
    setLoading(true);
    setError("");
    try {
      const [u, o, l, pkg] = await Promise.all([
        api.adminUsers(session.user_id),
        api.adminRecharges(session.user_id),
        api.adminOpLogs(100),
        api.vipPackages(),
      ]);
      setUsers(u.data || []);
      setOrders(o.data || []);
      setLogs(l.data || []);
      const list = pkg.data?.packages || [];
      setPackages(list);
      if (list.length && !list.some((p) => p.id === packageId) && packageId !== "custom") {
        setPackageId(list.find((p) => p.id === "vip_month")?.id || list[0].id);
      }
    } catch (e) {
      setError(e.message);
      if (String(e.message).includes("管理员")) {
        setTimeout(() => navigate("/admin/login"), 1200);
      }
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
  }, [q, vipFilter]);

  useEffect(() => {
    setOrderPage(1);
  }, [orderFilter, q]);

  const filteredUsers = useMemo(() => {
    const keyword = q.trim().toLowerCase();
    const now = Date.now();
    return users.filter((u) => {
      if (keyword) {
        const hay = `${u.user_id} ${u.username || ""} ${u.nickname || ""} ${u.email || ""}`.toLowerCase();
        if (!hay.includes(keyword)) return false;
      }
      const exp = parseExpire(u.vip_expire_at);
      const ms = exp ? exp.getTime() - now : null;
      if (vipFilter === "vip" && !u.is_vip) return false;
      if (vipFilter === "normal" && u.is_vip) return false;
      if (vipFilter === "expiring") {
        if (!u.is_vip || ms == null || ms < 0 || ms > 7 * 24 * 60 * 60 * 1000) return false;
      }
      if (vipFilter === "expired") {
        if (!exp || ms == null || ms >= 0) return false;
      }
      return true;
    });
  }, [users, q, vipFilter]);

  const filteredOrders = useMemo(() => {
    const keyword = q.trim().toLowerCase();
    return orders.filter((o) => {
      if (orderFilter !== "all" && o.status !== orderFilter) return false;
      if (!keyword) return true;
      const hay = `${o.id} ${o.user_id} ${o.package_name || ""} ${o.out_trade_no || ""}`.toLowerCase();
      return hay.includes(keyword);
    });
  }, [orders, orderFilter, q]);

  const userPages = Math.max(1, Math.ceil(filteredUsers.length / PAGE_SIZE));
  const orderPages = Math.max(1, Math.ceil(filteredOrders.length / PAGE_SIZE));
  const logPages = Math.max(1, Math.ceil(logs.length / PAGE_SIZE));
  const pageUsers = filteredUsers.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
  const pageOrders = filteredOrders.slice((orderPage - 1) * PAGE_SIZE, orderPage * PAGE_SIZE);
  const pageLogs = logs.slice((logPage - 1) * PAGE_SIZE, logPage * PAGE_SIZE);

  const pageIds = pageUsers.map((u) => u.user_id);
  const allPageSelected = pageIds.length > 0 && pageIds.every((id) => selected.has(id));

  const vipCount = users.filter((u) => u.is_vip).length;
  const paidCount = orders.filter((o) => o.status === "paid").length;
  const pendingCount = orders.filter((o) => o.status === "pending").length;

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

  const openDrawer = async (user) => {
    setDrawerUser(user);
    setDrawerData(null);
    setDrawerLoading(true);
    try {
      const res = await api.adminUserDetail(user.user_id);
      setDrawerData(res.data || null);
    } catch (e) {
      setError(e.message);
    } finally {
      setDrawerLoading(false);
    }
  };

  const runGrant = async (userIds) => {
    setBusy(true);
    setError("");
    setOkMsg("");
    try {
      const body = {
        admin_user_id: session.user_id,
        days: grantDays,
        package_id: packageId === "custom" ? "" : packageId,
      };
      if (userIds.length === 1) {
        await api.adminGrantVip({ ...body, user_id: userIds[0] });
        setOkMsg(`已开通 / 续期 ${grantDays} 天 VIP`);
      } else {
        await api.adminGrantVipBatch({ ...body, user_ids: userIds });
        setOkMsg(`已为 ${userIds.length} 名用户开通 ${grantDays} 天 VIP`);
      }
      setSelected(new Set());
      setConfirm(null);
      await load();
      if (drawerUser && userIds.includes(drawerUser.user_id)) {
        openDrawer(drawerUser);
      }
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const runRevoke = async (userId) => {
    setBusy(true);
    setError("");
    setOkMsg("");
    try {
      await api.adminRevokeVip({
        admin_user_id: session.user_id,
        user_id: userId,
      });
      setOkMsg("已取消 VIP");
      setConfirm(null);
      await load();
      if (drawerUser?.user_id === userId) openDrawer(drawerUser);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const askGrant = (user) => {
    const who = user.username || `用户 ${user.user_id}`;
    const userOrders = orders.filter((o) => o.user_id === user.user_id);
    const paid = userOrders.filter((o) => o.status === "paid").length;
    const pending = userOrders.filter((o) => o.status === "pending").length;
    const payHint =
      paid > 0
        ? `系统内已有 ${paid} 笔已支付订单`
        : pending > 0
          ? `无已支付订单，但有 ${pending} 笔待支付`
          : "系统内暂无充值订单";
    setConfirm({
      title: user.is_vip ? "确认续期 VIP" : "确认开通 VIP",
      message: `用户：${who}（ID ${user.user_id}）\n套餐：${grantLabel}\n订单情况：${payHint}\n\n请确认已核对付款后再继续。`,
      confirmText: user.is_vip ? "确认续期" : "确认开通",
      onConfirm: () => runGrant([user.user_id]),
    });
  };

  const askBatchGrant = () => {
    const ids = [...selected];
    if (!ids.length) return;
    setConfirm({
      title: "批量开通 VIP",
      message: `将为选中的 ${ids.length} 名用户开通：${grantLabel}\n请确认无误后再继续。`,
      confirmText: "确认批量开通",
      onConfirm: () => runGrant(ids),
    });
  };

  const askRevoke = (user) => {
    const who = user.username || `用户 ${user.user_id}`;
    setConfirm({
      title: "确认取消 VIP",
      message: `确定取消「${who}」的 VIP 吗？取消后对方将立即失去会员权益。`,
      confirmText: "确认取消",
      danger: true,
      onConfirm: () => runRevoke(user.user_id),
    });
  };

  const exportExcel = () => {
    if (tab === "orders") {
      downloadCsv("充值订单.csv", [
        ["单号", "用户ID", "套餐", "金额", "天数", "状态", "渠道", "时间", "商户单号"],
        ...filteredOrders.map((o) => [
          o.id,
          o.user_id,
          o.package_name,
          o.amount,
          o.days,
          statusLabel(o.status),
          channelLabel(o.channel),
          formatDate(o.created_at, true),
          o.out_trade_no || "",
        ]),
      ]);
      return;
    }
    if (tab === "logs") {
      downloadCsv("操作日志.csv", [
        ["时间", "管理员", "动作", "目标用户", "详情"],
        ...logs.map((r) => [
          formatDate(r.created_at, true),
          r.admin_username,
          actionLabel(r.action),
          r.target_username || r.target_user_id || "",
          r.detail,
        ]),
      ]);
      return;
    }
    downloadCsv("用户与VIP.csv", [
      ["ID", "用户名", "昵称", "邮箱", "VIP", "到期时间"],
      ...filteredUsers.map((u) => [
        u.user_id,
        u.username,
        u.nickname || "",
        u.email || "",
        u.is_vip ? "是" : "否",
        u.is_vip ? formatDate(u.vip_expire_at, true) : "—",
      ]),
    ]);
  };

  const renderPager = (current, total, onChange) => (
    <div className="admin-pager">
      <span>
        第 {current} / {total} 页
      </span>
      <div className="admin-pager-btns">
        <button type="button" className="admin-btn admin-btn-ghost" disabled={current <= 1} onClick={() => onChange(current - 1)}>
          上一页
        </button>
        <button
          type="button"
          className="admin-btn admin-btn-ghost"
          disabled={current >= total}
          onClick={() => onChange(current + 1)}
        >
          下一页
        </button>
      </div>
    </div>
  );

  return (
    <div className="admin-vip-page admin-vip-page-wide">
      <header className="admin-vip-toolbar">
        <div className="admin-vip-heading">
          <h1 className="admin-vip-title">用户与 VIP</h1>
          <div className="admin-vip-stats">
            <span>
              总用户 <b>{users.length}</b>
            </span>
            <span>
              VIP 用户 <b>{vipCount}</b>
            </span>
            <span>
              已支付订单 <b>{paidCount}</b>
            </span>
            <span className={pendingCount ? "warn" : ""}>
              待支付订单 <b>{pendingCount}</b>
            </span>
          </div>
        </div>
        <div className="admin-vip-controls">
          <label className="admin-pkg-field">
            <span>开通套餐</span>
            <select value={packageId} onChange={(e) => setPackageId(e.target.value)}>
              {packages.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} · {p.days}天
                </option>
              ))}
              <option value="custom">自定义天数</option>
            </select>
          </label>
          {packageId === "custom" ? (
            <label className="admin-days-field">
              <span>天数</span>
              <input
                type="number"
                min={1}
                value={customDays}
                onChange={(e) => setCustomDays(e.target.value)}
              />
              <em>天</em>
            </label>
          ) : null}
          <button type="button" className="admin-btn admin-btn-ghost" onClick={exportExcel}>
            导出 Excel
          </button>
        </div>
      </header>

      <div className="admin-toolbar-row">
        <input
          className="admin-search"
          type="search"
          placeholder={tab === "orders" ? "搜索单号 / 用户 / 套餐" : "搜索用户名 / ID / 邮箱"}
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        {tab === "users" ? (
          <select className="admin-filter" value={vipFilter} onChange={(e) => setVipFilter(e.target.value)}>
            <option value="all">全部状态</option>
            <option value="vip">仅 VIP</option>
            <option value="normal">仅普通</option>
            <option value="expiring">7 天内到期</option>
            <option value="expired">已过期</option>
          </select>
        ) : null}
        {tab === "orders" ? (
          <select className="admin-filter" value={orderFilter} onChange={(e) => setOrderFilter(e.target.value)}>
            <option value="all">全部订单</option>
            <option value="paid">已支付</option>
            <option value="pending">待支付</option>
            <option value="cancelled">已取消</option>
            <option value="closed">已关闭</option>
          </select>
        ) : null}
        {tab === "users" && selected.size > 0 ? (
          <button type="button" className="admin-btn admin-btn-primary" onClick={askBatchGrant}>
            批量开通（{selected.size}）
          </button>
        ) : null}
      </div>

      {error && <div className="form-error">{error}</div>}
      {okMsg && <div className="form-ok">{okMsg}</div>}

      <div className="admin-tabs" role="tablist">
        <button type="button" role="tab" className={tab === "users" ? "on" : ""} onClick={() => setTab("users")}>
          用户列表
        </button>
        <button type="button" role="tab" className={tab === "orders" ? "on" : ""} onClick={() => setTab("orders")}>
          充值订单
        </button>
        <button type="button" role="tab" className={tab === "logs" ? "on" : ""} onClick={() => setTab("logs")}>
          操作日志
        </button>
      </div>

      {loading ? (
        <p className="admin-vip-loading">加载中…</p>
      ) : tab === "users" ? (
        <>
          <div className="admin-panel">
            <table className="admin-table admin-table-users">
              <thead>
                <tr>
                  <th className="th-check">
                    <input type="checkbox" checked={allPageSelected} onChange={togglePage} aria-label="全选本页" />
                  </th>
                  <th>ID</th>
                  <th>用户</th>
                  <th>VIP</th>
                  <th>到期</th>
                  <th className="th-actions">操作</th>
                </tr>
              </thead>
              <tbody>
                {pageUsers.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="admin-empty">
                      <div className="admin-empty-box">
                        <strong>暂无匹配用户</strong>
                        <span>试试调整搜索关键词或筛选条件</span>
                      </div>
                    </td>
                  </tr>
                ) : (
                  pageUsers.map((u) => {
                    const expire = expireMeta(u.vip_expire_at, u.is_vip);
                    return (
                      <tr key={u.user_id}>
                        <td className="td-check">
                          <input
                            type="checkbox"
                            checked={selected.has(u.user_id)}
                            onChange={() => toggleOne(u.user_id)}
                            aria-label={`选择 ${u.username}`}
                          />
                        </td>
                        <td className="td-mono">{u.user_id}</td>
                        <td>
                          <button type="button" className="admin-user-link" onClick={() => openDrawer(u)}>
                            <strong>{u.username}</strong>
                            {u.nickname && u.nickname !== u.username ? <span>{u.nickname}</span> : null}
                          </button>
                        </td>
                        <td>
                          <span className={`admin-pill ${u.is_vip ? "vip" : "no"}`}>
                            {u.is_vip ? "VIP" : "普通"}
                          </span>
                        </td>
                        <td className={expire.className}>
                          {expire.tip ? (
                            <span className="admin-tip" data-tip={expire.tip} title={expire.tip}>
                              {expire.text}
                            </span>
                          ) : (
                            expire.text
                          )}
                        </td>
                        <td className="td-actions">
                          <div className="admin-row-actions">
                            <button type="button" className="admin-btn admin-btn-primary" onClick={() => askGrant(u)}>
                              {u.is_vip ? "续期" : "开通"}
                            </button>
                            <button
                              type="button"
                              className="admin-btn admin-btn-ghost"
                              disabled={!u.is_vip}
                              onClick={() => askRevoke(u)}
                            >
                              取消
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
          {filteredUsers.length > 0 ? renderPager(page, userPages, setPage) : null}
        </>
      ) : tab === "orders" ? (
        <>
          <div className="admin-panel">
            <table className="admin-table admin-table-orders">
              <thead>
                <tr>
                  <th>单号</th>
                  <th>用户</th>
                  <th>套餐</th>
                  <th>金额</th>
                  <th>状态</th>
                  <th>渠道</th>
                  <th>时间</th>
                  <th>商户单号</th>
                </tr>
              </thead>
              <tbody>
                {pageOrders.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="admin-empty">
                      <div className="admin-empty-box">
                        <strong>暂无订单</strong>
                        <span>用户完成充值后会显示在这里</span>
                      </div>
                    </td>
                  </tr>
                ) : (
                  pageOrders.map((o) => (
                    <tr key={o.id}>
                      <td className="td-mono">{o.id}</td>
                      <td className="td-mono">{o.user_id}</td>
                      <td>{o.package_name}</td>
                      <td className="td-amount">¥{o.amount}</td>
                      <td>
                        <span className={`admin-pill status-badge status-${o.status}`}>
                          {statusLabel(o.status)}
                        </span>
                      </td>
                      <td>{channelLabel(o.channel)}</td>
                      <td className="td-muted">{formatDate(o.created_at, true)}</td>
                      <td className="td-mono td-trade" title={o.out_trade_no || ""}>
                        {shortTradeNo(o.out_trade_no)}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
          {filteredOrders.length > 0 ? renderPager(orderPage, orderPages, setOrderPage) : null}
        </>
      ) : (
        <>
          <div className="admin-panel">
            <table className="admin-table">
              <thead>
                <tr>
                  <th>时间</th>
                  <th>管理员</th>
                  <th>动作</th>
                  <th>目标用户</th>
                  <th>详情</th>
                </tr>
              </thead>
              <tbody>
                {pageLogs.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="admin-empty">
                      <div className="admin-empty-box">
                        <strong>暂无操作日志</strong>
                        <span>开通、续期、取消 VIP 后会自动记录</span>
                      </div>
                    </td>
                  </tr>
                ) : (
                  pageLogs.map((r) => (
                    <tr key={r.id}>
                      <td className="td-muted">{formatDate(r.created_at, true)}</td>
                      <td>{r.admin_username || r.admin_user_id}</td>
                      <td>
                        <span className="admin-pill">{actionLabel(r.action)}</span>
                      </td>
                      <td>{r.target_username || (r.target_user_id ? `ID ${r.target_user_id}` : "—")}</td>
                      <td className="td-muted">{r.detail || "—"}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
          {logs.length > 0 ? renderPager(logPage, logPages, setLogPage) : null}
        </>
      )}

      <ConfirmModal
        open={Boolean(confirm)}
        title={confirm?.title}
        message={confirm?.message}
        confirmText={confirm?.confirmText}
        danger={confirm?.danger}
        busy={busy}
        onCancel={() => !busy && setConfirm(null)}
        onConfirm={confirm?.onConfirm}
      />

      {drawerUser ? (
        <div className="admin-drawer-mask" onClick={() => setDrawerUser(null)}>
          <aside className="admin-drawer" onClick={(e) => e.stopPropagation()}>
            <header className="admin-drawer-head">
              <div>
                <h2>{drawerData?.user?.username || drawerUser.username}</h2>
                <p>
                  ID {drawerUser.user_id}
                  {drawerData?.user?.email ? ` · ${drawerData.user.email}` : ""}
                </p>
              </div>
              <button type="button" className="admin-btn admin-btn-ghost" onClick={() => setDrawerUser(null)}>
                关闭
              </button>
            </header>
            {drawerLoading ? (
              <p className="admin-vip-loading">加载详情…</p>
            ) : (
              <div className="admin-drawer-body">
                <div className="admin-drawer-meta">
                  <span className={`admin-pill ${drawerData?.user?.is_vip ? "vip" : "no"}`}>
                    {drawerData?.user?.is_vip ? "VIP" : "普通"}
                  </span>
                  {(() => {
                    const expire = expireMeta(
                      drawerData?.user?.vip_expire_at,
                      drawerData?.user?.is_vip
                    );
                    return (
                      <span className={expire.className}>
                        {expire.tip ? (
                          <span className="admin-tip" data-tip={expire.tip} title={expire.tip}>
                            到期 {expire.text}
                          </span>
                        ) : (
                          <>到期 {expire.text}</>
                        )}
                      </span>
                    );
                  })()}
                </div>

                <h3>VIP 操作历史</h3>
                {(drawerData?.vip_history || []).length === 0 ? (
                  <p className="admin-drawer-empty">暂无 VIP 操作记录</p>
                ) : (
                  <ul className="admin-drawer-list">
                    {drawerData.vip_history.map((h) => (
                      <li key={h.id}>
                        <strong>{actionLabel(h.action)}</strong>
                        <span>{h.detail}</span>
                        <em>
                          {h.admin_username} · {formatDate(h.created_at, true)}
                        </em>
                      </li>
                    ))}
                  </ul>
                )}

                <h3>充值订单</h3>
                {(drawerData?.orders || []).length === 0 ? (
                  <p className="admin-drawer-empty">暂无充值订单</p>
                ) : (
                  <ul className="admin-drawer-list">
                    {drawerData.orders.map((o) => (
                      <li key={o.id}>
                        <strong>
                          #{o.id} {o.package_name}
                        </strong>
                        <span>
                          ¥{o.amount} · {channelLabel(o.channel)} ·{" "}
                          <i className={`admin-pill status-badge status-${o.status}`}>{statusLabel(o.status)}</i>
                        </span>
                        <em>{formatDate(o.created_at, true)}</em>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </aside>
        </div>
      ) : null}
    </div>
  );
}
