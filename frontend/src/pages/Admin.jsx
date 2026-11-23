import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, getSession } from "../api";

export default function Admin() {
  const navigate = useNavigate();
  const session = getSession();
  const [users, setUsers] = useState([]);
  const [orders, setOrders] = useState([]);
  const [days, setDays] = useState(30);
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
        setTimeout(() => navigate("/profile"), 1200);
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!session?.user_id) {
      navigate("/login", { replace: true });
      return;
    }
    load();
  }, [session?.user_id]);

  const grant = async (userId) => {
    setOkMsg("");
    setError("");
    try {
      await api.adminGrantVip({
        admin_user_id: session.user_id,
        user_id: userId,
        days: Number(days) || 30,
      });
      setOkMsg(`已给用户 ${userId} 开通 ${days} 天 VIP`);
      load();
    } catch (e) {
      setError(e.message);
    }
  };

  const revoke = async (userId) => {
    setOkMsg("");
    setError("");
    try {
      await api.adminRevokeVip({
        admin_user_id: session.user_id,
        user_id: userId,
      });
      setOkMsg(`已取消用户 ${userId} 的 VIP`);
      load();
    } catch (e) {
      setError(e.message);
    }
  };

  return (
    <div className="page-scroll profile-page">
      <div className="card profile-hero">
        <div>
          <h1 style={{ margin: "0 0 6px" }}>管理后台</h1>
          <p className="profile-desc">开通 / 取消 VIP，查看充值订单</p>
        </div>
      </div>

      <div className="card profile-form" style={{ marginBottom: 16 }}>
        <label>开通天数</label>
        <input
          type="number"
          min={1}
          value={days}
          onChange={(e) => setDays(e.target.value)}
          style={{ maxWidth: 120, marginLeft: 8 }}
        />
        {error && <div className="form-error">{error}</div>}
        {okMsg && <div className="form-ok">{okMsg}</div>}
      </div>

      {loading ? (
        <p style={{ color: "#636e72" }}>加载中…</p>
      ) : (
        <>
          <div className="card" style={{ marginBottom: 16, overflowX: "auto" }}>
            <h2 className="panel-title">用户列表</h2>
            <table className="admin-table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>用户名</th>
                  <th>昵称</th>
                  <th>VIP</th>
                  <th>到期</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.user_id}>
                    <td>{u.user_id}</td>
                    <td>{u.username}</td>
                    <td>{u.nickname}</td>
                    <td>{u.is_vip ? "是" : "否"}</td>
                    <td>{u.vip_expire_at ? u.vip_expire_at.slice(0, 10) : "-"}</td>
                    <td>
                      <button type="button" className="btn-primary" onClick={() => grant(u.user_id)}>
                        开通
                      </button>{" "}
                      <button type="button" className="logout-btn" onClick={() => revoke(u.user_id)}>
                        取消
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="card" style={{ overflowX: "auto" }}>
            <h2 className="panel-title">充值订单</h2>
            <table className="admin-table">
              <thead>
                <tr>
                  <th>单号</th>
                  <th>商户单号</th>
                  <th>用户</th>
                  <th>套餐</th>
                  <th>金额</th>
                  <th>状态</th>
                  <th>渠道</th>
                  <th>时间</th>
                </tr>
              </thead>
              <tbody>
                {orders.map((o) => (
                  <tr key={o.id}>
                    <td>{o.id}</td>
                    <td>{o.out_trade_no || "-"}</td>
                    <td>{o.user_id}</td>
                    <td>{o.package_name}</td>
                    <td>¥{o.amount}</td>
                    <td>{o.status === "paid" ? "已支付" : o.status === "pending" ? "待支付" : o.status}</td>
                    <td>{o.channel || "-"}</td>
                    <td>{o.created_at ? o.created_at.slice(0, 19).replace("T", " ") : "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
