import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, clearSession, getSession, setSession } from "../api";

export default function Profile() {
  const navigate = useNavigate();
  const session = getSession();
  const [profile, setProfile] = useState(null);
  const [packages, setPackages] = useState([]);
  const [payReady, setPayReady] = useState(false);
  const [alipayReady, setAlipayReady] = useState(false);
  const [wechatReady, setWechatReady] = useState(false);
  const [payChannel, setPayChannel] = useState("alipay");
  const [wechatQr, setWechatQr] = useState("");
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
    const ali = Boolean(pkg.data?.channels?.alipay ?? pkg.data?.alipay_ready);
    const wx = Boolean(pkg.data?.channels?.wechat ?? pkg.data?.wechat_ready);
    setAlipayReady(ali);
    setWechatReady(wx);
    setPayReady(Boolean(pkg.data?.pay_ready) || ali || wx);
    // 未配置微信时默认支付宝，界面也不展示通道切换
    setPayChannel(wx && !ali ? "wechat" : "alipay");
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
      if (e.key === "apex_user_session" || e.key === "apex_user") {
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

  const openPayResult = (data) => {
    const channel = data?.channel || payChannel;
    if (channel === "wechat") {
      const codeUrl = data?.code_url;
      if (!codeUrl) throw new Error("未返回微信收款码，请检查微信商户配置");
      setWechatQr(codeUrl);
      setOkMsg("请用微信扫码支付；付完后刷新本页查看 VIP 状态");
      return;
    }
    const payUrl = data?.pay_url;
    if (!payUrl) throw new Error("未返回支付链接，请检查支付宝商户配置");
    setOkMsg("正在跳转支付宝付款…支付成功后自动开通 VIP");
    window.location.href = payUrl;
  };

  const buy = async (packageId) => {
    const current = getSession();
    if (!current?.user_id) return;
    if (payChannel === "alipay" && !alipayReady) {
      setError("支付宝未配置，请改选微信或联系管理员");
      return;
    }
    if (payChannel === "wechat" && !wechatReady) {
      setError("微信支付未配置，请改选支付宝或联系管理员");
      return;
    }
    setPaying(packageId);
    setError("");
    setOkMsg("");
    setWechatQr("");
    try {
      const res = await api.vipRecharge({
        user_id: current.user_id,
        package_id: packageId,
        channel: payChannel,
      });
      openPayResult(res.data);
    } catch (err) {
      setError(err.message);
    } finally {
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
    setWechatQr("");
    try {
      const res = await api.vipContinuePay(orderId, current.user_id);
      openPayResult(res.data);
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
        <h2 className="panel-title">
          开通 VIP{alipayReady && !wechatReady ? "（支付宝充值）" : ""}
        </h2>
        <p className="profile-desc" style={{ marginBottom: 12 }}>
          VIP：更高对话/生图额度，解锁 AI 视频与 PPT 下载。支付成功后自动开通。
          {!loading && payReady && alipayReady && !wechatReady && (
            <span style={{ color: "#636e72", display: "block", marginTop: 6 }}>
              支付宝参数已就绪。若开放平台应用仍在「审核中」，正式收款需等审核通过；此前可用管理端手动开通 VIP。
            </span>
          )}
          {!loading && payReady && wechatReady && (
            <span style={{ color: "#636e72", display: "block", marginTop: 6 }}>
              已接入{alipayReady ? " 支付宝" : ""}
              {alipayReady ? " /" : ""} 微信。选好支付方式后再点套餐付款。
            </span>
          )}
          {!loading && !payReady && (
            <span style={{ color: "#c0392b", display: "block", marginTop: 6 }}>
              服务器未读到完整支付宝参数（APP_ID + 密钥文件）。请确认云主机
              <code> backend/.env </code>
              与
              <code> backend/keys/ </code>
              已配置并已重启服务；期间可由管理端开通 VIP。
            </span>
          )}
        </p>
        {payReady && wechatReady && (
          <div className="pay-channel" style={{ marginBottom: 14, display: "flex", gap: 16 }}>
            <label style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <input
                type="radio"
                name="payChannel"
                value="alipay"
                checked={payChannel === "alipay"}
                disabled={!alipayReady}
                onChange={() => setPayChannel("alipay")}
              />
              支付宝{!alipayReady ? "（未配置）" : ""}
            </label>
            <label style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <input
                type="radio"
                name="payChannel"
                value="wechat"
                checked={payChannel === "wechat"}
                onChange={() => setPayChannel("wechat")}
              />
              微信支付
            </label>
          </div>
        )}
        {wechatQr && (
          <div className="wechat-qr card" style={{ marginBottom: 16, textAlign: "center" }}>
            <p className="profile-desc">请使用微信扫一扫完成支付</p>
            <img
              alt="微信支付二维码"
              width={220}
              height={220}
              src={`https://api.qrserver.com/v1/create-qr-code/?size=220x220&data=${encodeURIComponent(wechatQr)}`}
            />
            <div style={{ marginTop: 10 }}>
              <button type="button" className="btn-primary" onClick={() => refresh()}>
                我已支付，刷新状态
              </button>
              <button
                type="button"
                className="logout-btn"
                style={{ marginLeft: 8 }}
                onClick={() => setWechatQr("")}
              >
                关闭
              </button>
            </div>
          </div>
        )}
        <div className="vip-packages">
          {packages.map((p) => (
            <div key={p.id} className="vip-pack card">
              <strong>{p.name}</strong>
              <div className="vip-price">¥{p.price}</div>
              <p>{p.desc}</p>
              <button
                type="button"
                className="btn-primary"
                disabled={!!paying || loading || !payReady}
                onClick={() => buy(p.id)}
              >
                {paying === p.id
                  ? "创建订单…"
                  : !payReady
                    ? "待配置支付"
                    : payChannel === "wechat" && wechatReady
                      ? "微信扫码支付"
                      : "去支付宝支付"}
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
                        {o.channel === "wechat"
                          ? " · 微信"
                          : o.channel === "alipay"
                            ? " · 支付宝"
                            : o.channel
                              ? ` · ${o.channel}`
                              : ""}
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
