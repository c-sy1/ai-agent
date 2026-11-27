import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, getSession } from "../api";

function shortTradeNo(no) {
  if (!no) return "-";
  if (no.length <= 14) return no;
  return `${no.slice(0, 8)}…${no.slice(-4)}`;
}

function statusLabel(status) {
  if (status === "paid") return "已支付";
  if (status === "pending") return "待支付";
  if (status === "cancelled") return "已取消";
  return status || "-";
}

export default function Admin() {
  const navigate = useNavigate();
  const session = getSession();
  const [users, setUsers] = useState([]);
  const [orders, setOrders] = useState([]);
  const [days, setDays] = useState(30);
  const [tab, setTab] = useState("users");
  const [error, setError] = useState("");
  const [okMsg, setOkMsg] = useState("");
  const [loading, setLoading] = useState(true);

  const load = async () => {
    if (!session?.user_id) return;
    setLoading(true);
    setError("");
    try {
      const [u, o] = await Promise.all([
        api.adminUsers(session.user_id),
        api.adminRecharges(session.user_id),
      ]);
      setUsers(u.data || []);
      setOrders(o.data || []);
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

  const grant = async (user) => {
    const userId = user.user_id;
    const d = Number(days) || 30;
    const who = user.username || `用户 ${userId}`;
    const userOrders = (orders || []).filter((o) => o.user_id === userId);
    const paid = userOrders.filter((o) => o.status === "paid");
    const pending = userOrders.filter((o) => o.status === "pending");
    const payHint =
      paid.length > 0
        ? `系统内已有 ${paid.length} 笔「已支付」订单`
        : pending.length > 0
          ? `系统内没有已支付订单，但有 ${pending.length} 笔「待支付」`
          : "系统内没有任何充值订单（用户很可能尚未付款）";

    if (
      !window.confirm(
        `请先确认用户是否已经付款\n\n用户：${who}（ID ${userId}）\n当前 VIP：${user.is_vip ? "是" : "否"}\n订单情况：${payHint}\n\n未付款请点「取消」；已核对到账或需补开再点「确定」。`
      )
    ) {
      return;
    }
    if (!window.confirm(`二次确认：给「${who}」开通 ${d} 天 VIP？`)) return;

    setOkMsg("");
    setError("");
    try {
      await api.adminGrantVip({
        admin_user_id: session.user_id,
        user_id: userId,
        days: d,
      });
      setOkMsg(`已给 ${who} 开通 ${d} 天 VIP`);
      load();
    } catch (e) {
      setError(e.message);
    }
  };

  const revoke = async (userId, username) => {
    const who = username || `用户 ${userId}`;
    if (!window.confirm(`确认取消「${who}」的 VIP？`)) return;
    setOkMsg("");
    setError("");
    try {
      await api.adminRevokeVip({
        admin_user_id: session.user_id,
        user_id: userId,
      });
      setOkMsg(`已取消 ${who} 的 VIP`);
      load();
    } catch (e) {
      setError(e.message);
    }
  };

  const vipCount = users.filter((u) => u.is_vip).length;
  const paidCount = orders.filter((o) => o.status === "paid").length;
  const pendingCount = orders.filter((o) => o.status === "pending").length;

  return (
    <div className="admin-vip-page">
      <div className="admin-vip-toolbar">
        <div>
          <h1 className="admin-vip-title">用户与 VIP</h1>
          <p className="admin-vip-sub">
            用户 {users.length} · VIP {vipCount} · 已支付 {paidCount} · 待支付 {pendingCount}
          </p>
        </div>
        <label className="admin-days-field">
          <span>开通天数</span>
          <input
            type="number"
            min={1}
            value={days}
            onChange={(e) => setDays(e.target.value)}
          />
        </label>
      </div>

      {error && <div className="form-error">{error}</div>}
      {okMsg && <div className="form-ok">{okMsg}</div>}

      <div className="admin-tabs">
        <button
          type="button"
          className={tab === "users" ? "on" : ""}
          onClick={() => setTab("users")}
        >
          用户列表
        </button>
        <button
          type="button"
          className={tab === "orders" ? "on" : ""}
          onClick={() => setTab("orders")}
        >
          充值订单
        </button>
      </div>

      {loading ? (
        <p className="admin-vip-sub">加载中…</p>
      ) : tab === "users" ? (
        <div className="admin-panel">
          <table className="admin-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>用户</th>
                <th>VIP</th>
                <th>到期</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.user_id}>
                  <td>{u.user_id}</td>
                  <td>
                    <div className="admin-user-cell">
                      <strong>{u.username}</strong>
                      {u.nickname && u.nickname !== u.username ? (
                        <span>{u.nickname}</span>
                      ) : null}
                    </div>
                  </td>
                  <td>
                    <span className={`admin-pill ${u.is_vip ? "vip" : "no"}`}>
                      {u.is_vip ? "VIP" : "普通"}
                    </span>
                  </td>
                  <td>{u.vip_expire_at ? u.vip_expire_at.slice(0, 10) : "-"}</td>
                  <td>
                    <div className="admin-row-actions">
                      <button type="button" className="btn-primary" onClick={() => grant(u)}>
                        {u.is_vip ? "续期" : "开通"}
                      </button>
                      <button
                        type="button"
                        className="logout-btn"
                        disabled={!u.is_vip}
                        onClick={() => revoke(u.user_id, u.username)}
                      >
                        取消
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="admin-panel">
          <table className="admin-table">
            <thead>
              <tr>
                <th>单号</th>
                <th>用户</th>
                <th>套餐</th>
                <th>金额</th>
                <th>状态</th>
                <th>渠道</th>
                <th>时间</th>
                <th title="商户单号">商户单号</th>
              </tr>
            </thead>
            <tbody>
              {orders.length === 0 ? (
                <tr>
                  <td colSpan={8} className="admin-empty">
                    暂无订单
                  </td>
                </tr>
              ) : (
                orders.map((o) => (
                  <tr key={o.id}>
                    <td>{o.id}</td>
                    <td>{o.user_id}</td>
                    <td>{o.package_name}</td>
                    <td>¥{o.amount}</td>
                    <td>
                      <span className={`admin-pill status-${o.status}`}>
                        {statusLabel(o.status)}
                      </span>
                    </td>
                    <td>{o.channel === "alipay" ? "支付宝" : o.channel || "-"}</td>
                    <td>{o.created_at ? o.created_at.slice(0, 16).replace("T", " ") : "-"}</td>
                    <td title={o.out_trade_no || ""}>{shortTradeNo(o.out_trade_no)}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
