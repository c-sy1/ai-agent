import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, clearSession, getSession, setSession } from "../api";

export default function Profile() {
  const navigate = useNavigate();
  const session = getSession();
  const [profile, setProfile] = useState(null);
  const [packages, setPackages] = useState([]);
  const [payReady, setPayReady] = useState(false);
  const [orders, setOrders] = useState([]);
  const [nickname, setNickname] = useState("");
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [paying, setPaying] = useState("");
  const [error, setError] = useState("");
  const [okMsg, setOkMsg] = useState("");

  const refresh = async () => {
    const current = getSession();
    if (!current?.user_id) return;
    const [res, pkg, ord] = await Promise.all([
      api.profile(current.user_id),
      api.vipPackages(),
      api.vipOrders(current.user_id),
    ]);
    setProfile(res.data);
    setNickname(res.data.nickname || "");
    setEmail(res.data.email || "");
    setPackages(pkg.data?.packages || []);
    setPayReady(Boolean(pkg.data?.pay_ready));
    setOrders(ord.data || []);
    setSession({
      ...current,
      user_id: res.data.user_id,
      username: res.data.username,
      nickname: res.data.nickname,
      email: res.data.email,
      is_vip: res.data.is_vip,
      is_admin: res.data.is_admin,
      vip_expire_at: res.data.vip_expire_at,
    });
  };

  useEffect(() => {
    if (!session?.user_id) {
      navigate("/login", { replace: true });
      return;
    }
    setLoading(true);
    refresh()
      .then(() => {
        const paid = new URLSearchParams(window.location.search).get("pay");
        if (paid) {
          setOkMsg("已返回支付结果，若已付款 VIP 将自动开通；可刷新查看状态。");
          window.history.replaceState({}, "", "/profile");
        }
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));

    const onVisible = () => {
      if (document.visibilityState === "visible") {
        refresh().catch(() => {});
      }
    };
    const onStorage = (e) => {
      if (e.key === "apex_user") {
        const next = getSession();
        if (!next?.user_id) {
          navigate("/login", { replace: true });
          return;
        }
        refresh().catch((err) => setError(err.message));
      }
    };
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("storage", onStorage);
    return () => {
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("storage", onStorage);
    };
  }, [session?.user_id, navigate]);

  const save = async (e) => {
    e.preventDefault();
    const current = getSession();
    if (!current?.user_id) return;
    setSaving(true);
    setError("");
    setOkMsg("");
    try {
      const res = await api.updateProfile({
        user_id: current.user_id,
        nickname,
        email,
      });
      setProfile((p) => ({ ...p, ...res.data }));
      setSession({
        ...current,
        username: res.data.username,
        nickname: res.data.nickname,
        email: res.data.email,
      });
      setOkMsg("资料已保存");
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const buy = async (packageId) => {
    const current = getSession();
    if (!current?.user_id) return;
    setPaying(packageId);
    setError("");
    setOkMsg("");
    try {
      const res = await api.vipRecharge({
        user_id: current.user_id,
        package_id: packageId,
      });
      const payUrl = res.data?.pay_url;
      if (!payUrl) {
        throw new Error("未返回支付链接，请检查支付宝商户配置");
      }
      setOkMsg("正在跳转支付宝付款…支付成功后自动开通 VIP");
      window.location.href = payUrl;
    } catch (err) {
      setError(err.message);
      setPaying("");
    }
  };

  const cancelOrder = async (orderId) => {
    const current = getSession();
    if (!current?.user_id) return;
    setError("");
    setOkMsg("");
    try {
      await api.vipCancelOrder(orderId, current.user_id);
      setOkMsg("待支付订单已取消");
      await refresh();
    } catch (err) {
      setError(err.message);
    }
  };

  const continuePay = async (orderId) => {
    const current = getSession();
    if (!current?.user_id) return;
    setError("");
    setOkMsg("");
    try {
      const res = await api.vipContinuePay(orderId, current.user_id);
      const payUrl = res.data?.pay_url;
      if (!payUrl) throw new Error("未返回支付链接");
      setOkMsg("正在跳转支付宝…");
      window.location.href = payUrl;
    } catch (err) {
      setError(err.message);
    }
  };

  const logout = () => {
    clearSession();
    navigate("/login", { replace: true });
  };

  if (loading) {
    return (
      <div className="page-scroll">
        <p style={{ color: "#636e72" }}>加载个人主页…</p>
      </div>
    );
  }

  const display = profile?.nickname || profile?.username || "用户";
  const usage = profile?.usage;

  return (
    <div className="page-scroll profile-page">
      <div className="profile-hero card">
        <div className="profile-avatar">{display.slice(0, 1)}</div>
        <div>
          <h1 style={{ margin: "0 0 6px" }}>
            {display}
            {profile?.is_vip ? <span className="vip-badge">VIP</span> : null}
          </h1>
          <p className="profile-username">@{profile?.username}</p>
          <p className="profile-desc">
            {profile?.is_vip
              ? `VIP 有效至 ${profile.vip_expire_at ? profile.vip_expire_at.slice(0, 10) : "长期"}`
              : "普通用户 · 免费有日额度，视频/PPT 与高额度需开通 VIP"}
          </p>
        </div>
      </div>

      <div className="profile-stats">
        <div className="card profile-stat">
          <strong>{profile?.conversation_count ?? 0}</strong>
          <span>对话数</span>
        </div>
        <div className="card profile-stat">
          <strong>{profile?.is_vip ? "VIP" : "普通"}</strong>
          <span>会员状态</span>
        </div>
        <div className="card profile-stat">
          <strong>{profile?.created_at ? profile.created_at.slice(0, 10) : "-"}</strong>
          <span>注册日期</span>
        </div>
      </div>

      {usage ? (
        <div className="card profile-form" style={{ marginBottom: 16 }}>
          <h2 className="panel-title">今日用量</h2>
          <p className="profile-desc" style={{ marginBottom: 12 }}>
            免费用户每日有额度上限；用完可开通 VIP 继续畅用。
          </p>
          <div className="usage-grid">
            {[usage.chat, usage.image].filter(Boolean).map((u) => (
              <div key={u.feature} className="usage-item">
                <div className="usage-item-head">
                  <strong>{u.label}</strong>
                  <span>{u.unlimited ? "不限" : `${u.used} / ${u.limit}`}</span>
                </div>
                <div className="usage-bar">
                  <div
                    className="usage-bar-fill"
                    style={{
                      width: u.unlimited
                        ? "8%"
                        : `${Math.min(100, Math.round((u.used / Math.max(1, u.limit)) * 100))}%`,
                    }}
                  />
                </div>
                {!u.unlimited && u.remain === 0 ? (
                  <p className="usage-warn">今日已用完 · 开通 VIP 提升额度</p>
                ) : (
                  <p className="profile-desc" style={{ margin: "6px 0 0" }}>
                    {u.unlimited ? "VIP 高额度" : `剩余 ${u.remain} 次`}
                  </p>
                )}
              </div>
            ))}
          </div>
          <div className="benefit-compare">
            <div className="benefit-col">
              <h3>免费用户</h3>
              <ul>
                {(usage.benefits?.free || []).map((txt) => (
                  <li key={txt}>{txt}</li>
                ))}
              </ul>
            </div>
            <div className="benefit-col benefit-vip">
              <h3>VIP 会员</h3>
              <ul>
                {(usage.benefits?.vip || []).map((txt) => (
                  <li key={txt}>{txt}</li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      ) : null}

      <div className="card profile-form" style={{ marginBottom: 16 }}>
        <h2 className="panel-title">开通 VIP（支付宝充值）</h2>
        <p className="profile-desc" style={{ marginBottom: 12 }}>
          VIP：更高对话/生图额度，解锁 AI 视频与 PPT 下载。支付成功后自动开通。
          {!payReady && (
            <span style={{ color: "#c0392b", display: "block", marginTop: 6 }}>
              当前未配置支付宝商户参数，无法在线支付。请在 backend/.env 填写 ALIPAY_APP_ID 等；期间可由管理员后台开通。
            </span>
          )}
        </p>
        <div className="vip-packages">
          {packages.map((p) => (
            <div key={p.id} className="vip-pack card">
              <strong>{p.name}</strong>
              <div className="vip-price">¥{p.price}</div>
              <p>{p.desc}</p>
              <button
                type="button"
                className="btn-primary"
                disabled={!!paying || !payReady}
                onClick={() => buy(p.id)}
              >
                {paying === p.id ? "创建订单…" : payReady ? "去支付宝支付" : "待配置支付"}
              </button>
            </div>
          ))}
        </div>
        {(() => {
          const statusLabel = {
            paid: "已支付",
            pending: "待支付",
            cancelled: "已取消",
            closed: "已关闭",
          };
          const visible = orders.filter((o) => o.status === "paid" || o.status === "pending");
          if (visible.length === 0) {
            return (
              <p className="profile-desc" style={{ marginTop: 16 }}>
                暂无有效订单
              </p>
            );
          }
          return (
            <div className="order-block">
              <h3 className="panel-title">我的订单</h3>
              <div className="order-list">
                {visible.slice(0, 10).map((o) => (
                  <div key={o.id} className="order-row">
                    <div className="order-main">
                      <strong>{o.package_name}</strong>
                      <span className="order-date">
                        {o.created_at ? o.created_at.slice(0, 10) : "-"}
                      </span>
                    </div>
                    <div className="order-meta">
                      <span className="order-amount">¥{o.amount}</span>
                      <span className={`order-status status-${o.status}`}>
                        {statusLabel[o.status] || o.status}
                      </span>
                      {o.status === "pending" && (
                        <div className="order-actions">
                          <button
                            type="button"
                            className="btn-primary"
                            onClick={() => continuePay(o.id)}
                          >
                            继续支付
                          </button>
                          <button
                            type="button"
                            className="logout-btn"
                            onClick={() => cancelOrder(o.id)}
                          >
                            取消
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          );
        })()}
      </div>

      <form className="card profile-form" onSubmit={save}>
        <h2 className="panel-title">账号资料</h2>
        <div className="form-field">
          <label>用户名（登录名，不可改）</label>
          <input value={profile?.username || ""} disabled />
        </div>
        <div className="form-field">
          <label>昵称（主页显示名）</label>
          <input
            value={nickname}
            onChange={(e) => setNickname(e.target.value)}
            placeholder="显示名称"
            required
          />
        </div>
        <div className="form-field">
          <label>邮箱</label>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="name@example.com"
            required
          />
        </div>
        {error && <div className="form-error">{error}</div>}
        {okMsg && <div className="form-ok">{okMsg}</div>}
        <div className="profile-actions">
          <button type="submit" className="btn-primary" disabled={saving}>
            {saving ? "保存中…" : "保存资料"}
          </button>
          <button type="button" className="logout-btn profile-logout" onClick={logout}>
            退出登录
          </button>
        </div>
      </form>
    </div>
  );
}
