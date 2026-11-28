import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, clearSession, getSession, setSession } from "../api";

const ORDER_PAGE_SIZE = 3;

const FAQ_ITEMS = [
  {
    q: "支付成功后多久开通 VIP？",
    a: "支付宝/微信到账后一般会自动开通；若页面未刷新，可稍等片刻或手动刷新本页查看状态。",
  },
  {
    q: "可以退款吗？",
    a: "虚拟会员服务开通后原则上不支持无理由退款。若重复扣款或支付异常，请保留订单号联系管理员核对。",
  },
  {
    q: "优惠券怎么用？从哪获得？",
    a: "注册自动获赠新人券 APEX5；活动券 APEX10 可在个人中心领取一次。领取后 7 天内有效，每人每张限用 1 次。点选「可用」券后再支付即可抵扣。",
  },
  {
    q: "VIP 到期后会怎样？",
    a: "到期后恢复普通用户额度，视频与 PPT 专属能力将暂时不可用，续费后立即恢复。",
  },
];

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

function vipDaysLeft(iso) {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return Math.ceil((d.getTime() - Date.now()) / (24 * 60 * 60 * 1000));
}

function ProfileModal({ open, title, children, onClose, actions }) {
  if (!open) return null;
  return (
    <div className="profile-modal-mask" role="dialog" aria-modal="true" onClick={onClose}>
      <div className="profile-modal" onClick={(e) => e.stopPropagation()}>
        <header className="profile-modal-head">
          <h3>{title}</h3>
          <button type="button" className="logout-btn" onClick={onClose}>
            关闭
          </button>
        </header>
        <div className="profile-modal-body">{children}</div>
        {actions ? <div className="profile-modal-actions">{actions}</div> : null}
      </div>
    </div>
  );
}

export default function Profile() {
  const navigate = useNavigate();
  const session = getSession();
  const [profile, setProfile] = useState(null);
  const [packages, setPackages] = useState([]);
  const [campaignCoupons, setCampaignCoupons] = useState([]);
  const [myCoupons, setMyCoupons] = useState([]);
  const [couponRules, setCouponRules] = useState("");
  const [refundNote, setRefundNote] = useState("");
  const [claiming, setClaiming] = useState("");
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
  const [couponCode, setCouponCode] = useState("");
  const [couponInput, setCouponInput] = useState("");
  const [benefitDetail, setBenefitDetail] = useState(null);
  const [faqOpen, setFaqOpen] = useState(null);
  const [payToast, setPayToast] = useState(null);
  const [orderStatus, setOrderStatus] = useState("all");
  const [orderFrom, setOrderFrom] = useState("");
  const [orderTo, setOrderTo] = useState("");
  const [orderQ, setOrderQ] = useState("");
  const [orderPage, setOrderPage] = useState(1);
  const [orderDetail, setOrderDetail] = useState(null);

  const refresh = async () => {
    const current = getSession();
    if (!current?.user_id) return;
    const [res, pkg, ord, couponBag] = await Promise.all([
      api.profile(current.user_id),
      api.vipPackages(),
      api.vipOrders(current.user_id),
      api.vipCouponsMine().catch(() => ({ data: { mine: [], campaign: [], rules: "" } })),
    ]);
    setProfile(res.data);
    setNickname(res.data.nickname || "");
    setEmail(res.data.email || "");
    setPackages(pkg.data?.packages || []);
    setCampaignCoupons(couponBag.data?.campaign || pkg.data?.coupons || []);
    setMyCoupons(couponBag.data?.mine || []);
    setCouponRules(couponBag.data?.rules || pkg.data?.coupon_rules || "");
    setRefundNote(pkg.data?.refund_note || "");
    const ali = Boolean(pkg.data?.channels?.alipay ?? pkg.data?.alipay_ready);
    const wx = Boolean(pkg.data?.channels?.wechat ?? pkg.data?.wechat_ready);
    setAlipayReady(ali);
    setWechatReady(wx);
    setPayReady(Boolean(pkg.data?.pay_ready) || ali || wx);
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
          setPayToast({
            type: "ok",
            title: "已返回支付结果",
            message: "若已成功付款，VIP 将自动开通。可刷新本页确认状态。",
          });
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
      setPayToast({
        type: "ok",
        title: "请完成微信支付",
        message: "请使用微信扫码支付；付款成功后刷新本页查看 VIP 状态。",
      });
      return;
    }
    const payUrl = data?.pay_url;
    if (!payUrl) throw new Error("未返回支付链接，请检查支付宝商户配置");
    setPayToast({
      type: "ok",
      title: "正在跳转支付宝",
      message: "即将打开支付宝完成付款，支付成功后 VIP 会自动开通。",
    });
    setTimeout(() => {
      window.location.href = payUrl;
    }, 500);
  };

  const buy = async (packageId) => {
    const current = getSession();
    if (!current?.user_id) return;
    if (payChannel === "alipay" && !alipayReady) {
      setPayToast({ type: "err", title: "支付失败", message: "支付宝未配置，请改选微信或联系管理员" });
      return;
    }
    if (payChannel === "wechat" && !wechatReady) {
      setPayToast({ type: "err", title: "支付失败", message: "微信支付未配置，请改选支付宝或联系管理员" });
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
        coupon_code: couponCode || "",
      });
      openPayResult(res.data);
    } catch (err) {
      setPayToast({
        type: "err",
        title: "支付失败",
        message: err.message || "创建订单失败，请稍后重试",
      });
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
    setPaying(`order-${orderId}`);
    setError("");
    setOkMsg("");
    setWechatQr("");
    try {
      const res = await api.vipContinuePay(orderId, current.user_id);
      openPayResult(res.data);
    } catch (err) {
      setPayToast({
        type: "err",
        title: "继续支付失败",
        message: err.message || "请稍后重试",
      });
    } finally {
      setPaying("");
    }
  };

  const logout = () => {
    clearSession();
    navigate("/login", { replace: true });
  };

  const availableCoupons = useMemo(
    () => (myCoupons || []).filter((c) => c.status === "available"),
    [myCoupons]
  );

  const activeCoupon = useMemo(
    () => availableCoupons.find((c) => c.code === couponCode) || null,
    [availableCoupons, couponCode]
  );

  const formalOrders = useMemo(() => {
    return (orders || []).filter((o) => {
      const pid = (o.package_id || "").toLowerCase();
      const name = o.package_name || "";
      if (pid === "vip_test") return false;
      if (name.includes("支付测试") || name.includes("1分钱")) return false;
      return true;
    });
  }, [orders]);

  const filteredOrders = useMemo(() => {
    const kw = orderQ.trim().toLowerCase();
    return formalOrders.filter((o) => {
      if (orderStatus === "paid" && o.status !== "paid") return false;
      if (orderStatus === "cancelled" && o.status !== "cancelled") return false;
      if (orderStatus === "pending" && o.status !== "pending") return false;
      const day = (o.created_at || "").slice(0, 10);
      if (orderFrom && day && day < orderFrom) return false;
      if (orderTo && day && day > orderTo) return false;
      if (kw) {
        const hay = `${o.package_name || ""} ${o.out_trade_no || ""} ${o.id}`.toLowerCase();
        if (!hay.includes(kw)) return false;
      }
      return true;
    });
  }, [formalOrders, orderStatus, orderFrom, orderTo, orderQ]);

  const orderPages = Math.max(1, Math.ceil(filteredOrders.length / ORDER_PAGE_SIZE));
  const pageOrders = filteredOrders.slice(
    (orderPage - 1) * ORDER_PAGE_SIZE,
    orderPage * ORDER_PAGE_SIZE
  );

  useEffect(() => {
    setOrderPage(1);
  }, [orderStatus, orderFrom, orderTo, orderQ]);

  const pricedPackages = useMemo(() => {
    return packages.map((p) => {
      let payAmount = Number(p.price);
      let discount = 0;
      if (activeCoupon && payAmount >= Number(activeCoupon.min_amount)) {
        discount = Number(activeCoupon.off);
        payAmount = Math.max(0.01, Math.round((payAmount - discount) * 100) / 100);
      }
      return { ...p, payAmount, discount, couponOk: discount > 0 };
    });
  }, [packages, activeCoupon]);

  const applyCouponInput = () => {
    const code = couponInput.trim().toUpperCase();
    if (!code) {
      setCouponCode("");
      return;
    }
    const hit = availableCoupons.find((c) => c.code === code);
    if (!hit) {
      const owned = (myCoupons || []).find((c) => c.code === code);
      if (owned?.status === "used") {
        setPayToast({ type: "err", title: "无法使用", message: "该优惠券已使用，每人限用 1 次。" });
        return;
      }
      if (owned?.status === "expired") {
        setPayToast({ type: "err", title: "无法使用", message: "该优惠券已过期（领取后 7 天内有效）。" });
        return;
      }
      setPayToast({
        type: "err",
        title: "券包中没有此券",
        message: "请先领取活动券，或确认新人券是否已到账。",
      });
      return;
    }
    setCouponCode(hit.code);
    setOkMsg(`已选用优惠券 ${hit.code}`);
  };

  const claimCampaign = async (code) => {
    setClaiming(code);
    setError("");
    try {
      const res = await api.vipCouponClaim(code);
      setMyCoupons(res.data || []);
      setOkMsg(res.msg || `已领取 ${code}`);
      setCouponCode(code);
      setCouponInput(code);
    } catch (err) {
      setPayToast({ type: "err", title: "领取失败", message: err.message || "领取失败" });
    } finally {
      setClaiming("");
    }
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
  const daysLeft = profile?.is_vip ? vipDaysLeft(profile?.vip_expire_at) : null;
  const showExpireBanner = profile?.is_vip && daysLeft != null && daysLeft <= 7;
  const week = usage?.week || [];
  const weekMax = Math.max(1, ...week.map((d) => (d.chat || 0) + (d.image || 0)));
  const benefitDetails = usage?.benefit_details || { free: [], vip: [] };

  return (
    <div className="page-scroll profile-page">
      {showExpireBanner ? (
        <div className={`vip-expire-banner ${daysLeft < 0 ? "danger" : "warn"}`}>
          <strong>{daysLeft < 0 ? "VIP 已过期" : "VIP 即将到期"}</strong>
          <span>
            {daysLeft < 0
              ? `已过期 ${Math.abs(daysLeft)} 天，续费后可继续享受会员权益。`
              : daysLeft === 0
                ? "今天到期，建议尽快续费以免权益中断。"
                : `还剩 ${daysLeft} 天，到期日 ${profile.vip_expire_at?.slice(0, 10)}。`}
          </span>
          <a href="#vip-plans">去续费</a>
        </div>
      ) : null}

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
            免费用户每日有额度上限；VIP 对话额度不限。用完可开通 VIP 继续畅用。
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
                    className={`usage-bar-fill${u.unlimited ? " full" : ""}`}
                    style={{
                      width: u.unlimited
                        ? "100%"
                        : `${Math.min(100, Math.round((u.used / Math.max(1, u.limit)) * 100))}%`,
                    }}
                  />
                </div>
                {!u.unlimited && u.remain === 0 ? (
                  <p className="usage-warn">今日已用完 · 开通 VIP 提升额度</p>
                ) : (
                  <p className="profile-desc" style={{ margin: "6px 0 0" }}>
                    {u.unlimited ? "VIP 对话额度不限" : `剩余 ${u.remain} 次`}
                  </p>
                )}
              </div>
            ))}
          </div>

          <div className="usage-week-card">
            <div className="usage-week-head">
              <h3>近 7 天 AI 用量</h3>
              <span>
                对话 {usage.week_totals?.chat ?? 0} · 生图 {usage.week_totals?.image ?? 0}
              </span>
            </div>
            <div className="usage-week-bars">
              {week.map((d) => {
                const total = (d.chat || 0) + (d.image || 0);
                const h = Math.max(8, Math.round((total / weekMax) * 72));
                return (
                  <div key={d.day} className="usage-week-col" title={`${d.day}：对话 ${d.chat} / 生图 ${d.image}`}>
                    <div className="usage-week-bar" style={{ height: `${h}px` }} />
                    <em>{d.day.slice(5)}</em>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="benefit-compare">
            <div className="benefit-col">
              <h3>免费用户</h3>
              <ul>
                {(benefitDetails.free.length ? benefitDetails.free : (usage.benefits?.free || []).map((t) => ({ title: t, detail: t }))).map(
                  (item) => (
                    <li key={item.title}>
                      <button type="button" className="benefit-link" onClick={() => setBenefitDetail(item)}>
                        {item.title}
                      </button>
                    </li>
                  )
                )}
              </ul>
            </div>
            <div className="benefit-col benefit-vip">
              <h3>VIP 会员</h3>
              <ul>
                {(benefitDetails.vip.length ? benefitDetails.vip : (usage.benefits?.vip || []).map((t) => ({ title: t, detail: t }))).map(
                  (item) => (
                    <li key={item.title}>
                      <button type="button" className="benefit-link" onClick={() => setBenefitDetail(item)}>
                        {item.title}
                      </button>
                    </li>
                  )
                )}
              </ul>
            </div>
          </div>
          <p className="profile-desc" style={{ marginTop: 8 }}>
            点击权益条目可查看详细说明
          </p>
        </div>
      ) : null}

      <div className="card profile-form" style={{ marginBottom: 16 }} id="vip-plans">
        <h2 className="panel-title">
          开通 VIP{alipayReady && !wechatReady ? "（支付宝充值）" : ""}
        </h2>
        <p className="profile-desc" style={{ marginBottom: 12 }}>
          VIP：对话额度不限，更高生图额度，解锁 AI 视频与 PPT 下载。支付成功后自动开通。
          {refundNote ? (
            <span style={{ display: "block", marginTop: 6, color: "#636e72" }}>{refundNote}</span>
          ) : null}
          {!loading && !payReady && (
            <span style={{ color: "#c0392b", display: "block", marginTop: 6 }}>
              支付通道暂未就绪，期间可由管理端开通 VIP。
            </span>
          )}
        </p>

        <div className="coupon-box">
          <div className="coupon-box-top">
            <h3>我的优惠券</h3>
            <div className="coupon-apply">
              <input
                value={couponInput}
                onChange={(e) => setCouponInput(e.target.value)}
                placeholder="输入已有券码选用"
              />
              <button type="button" className="logout-btn" onClick={applyCouponInput}>
                选用
              </button>
              {couponCode ? (
                <button
                  type="button"
                  className="logout-btn"
                  onClick={() => {
                    setCouponCode("");
                    setCouponInput("");
                  }}
                >
                  清除
                </button>
              ) : null}
            </div>
          </div>
          {couponRules ? <p className="profile-desc coupon-rules">{couponRules}</p> : null}

          <div className="coupon-list">
            {myCoupons.length === 0 ? (
              <p className="profile-desc">暂无优惠券，注册用户会自动获赠新人券</p>
            ) : (
              myCoupons.map((c) => {
                const usable = c.status === "available";
                return (
                  <button
                    key={`${c.id}-${c.code}`}
                    type="button"
                    className={`coupon-card status-${c.status}${couponCode === c.code && usable ? " on" : ""}`}
                    disabled={!usable}
                    onClick={() => {
                      if (!usable) return;
                      setCouponCode(c.code);
                      setCouponInput(c.code);
                    }}
                  >
                    <strong>{c.label}</strong>
                    <span>{c.desc}</span>
                    <em>
                      {c.code}
                      {c.status === "available" && c.expire_at
                        ? ` · ${String(c.expire_at).slice(0, 10)} 前有效`
                        : c.status === "used"
                          ? " · 已使用"
                          : c.status === "expired"
                            ? " · 已过期"
                            : ""}
                    </em>
                  </button>
                );
              })
            )}
          </div>

          <div className="coupon-claim-row">
            <span>活动领取</span>
            {(campaignCoupons || [])
              .filter((c) => c.claimable)
              .map((c) => {
                const owned = (myCoupons || []).some((m) => m.code === c.code);
                return (
                  <button
                    key={c.code}
                    type="button"
                    className="logout-btn"
                    disabled={owned || claiming === c.code}
                    onClick={() => claimCampaign(c.code)}
                  >
                    {owned ? `已领 ${c.code}` : claiming === c.code ? "领取中…" : `领取 ${c.code}`}
                  </button>
                );
              })}
          </div>
        </div>

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
              <button type="button" className="logout-btn" style={{ marginLeft: 8 }} onClick={() => setWechatQr("")}>
                关闭
              </button>
            </div>
          </div>
        )}

        <div className="vip-packages">
          {pricedPackages.map((p) => (
            <div key={p.id} className={`vip-pack card${p.recommended ? " recommended" : ""}`}>
              {p.recommended ? <span className="vip-reco-tag">性价比推荐</span> : null}
              <strong>{p.name}</strong>
              <div className="vip-price">
                ¥{p.payAmount}
                {p.couponOk ? <s>¥{p.price}</s> : null}
              </div>
              <p>{p.desc}</p>
              {p.couponOk ? <p className="vip-coupon-hint">已抵扣 ¥{p.discount}</p> : null}
              <button
                type="button"
                className="btn-primary"
                disabled={!!paying || loading || !payReady}
                onClick={() => buy(p.id)}
              >
                {paying === p.id
                  ? "创建订单中…"
                  : !payReady
                    ? "待配置支付"
                    : payChannel === "wechat" && wechatReady
                      ? "微信扫码支付"
                      : "去支付宝支付"}
              </button>
            </div>
          ))}
        </div>

        <div className="order-block">
          <div className="order-block-head">
            <h3 className="panel-title">订单记录</h3>
            <span className="order-count">共 {filteredOrders.length} 笔</span>
          </div>

          <div className="order-filters">
            <div className="order-status-tabs">
              {[
                { id: "all", label: "全部" },
                { id: "paid", label: "已支付" },
                { id: "cancelled", label: "已取消" },
              ].map((t) => (
                <button
                  key={t.id}
                  type="button"
                  className={`order-status-tab${orderStatus === t.id ? " on" : ""}`}
                  onClick={() => setOrderStatus(t.id)}
                >
                  {t.label}
                </button>
              ))}
            </div>
            <div className="order-filter-row">
              <input
                type="search"
                className="order-search"
                placeholder="搜索套餐名称"
                value={orderQ}
                onChange={(e) => setOrderQ(e.target.value)}
              />
              <input
                type="date"
                className="order-date"
                value={orderFrom}
                onChange={(e) => setOrderFrom(e.target.value)}
                title="开始日期"
              />
              <input
                type="date"
                className="order-date"
                value={orderTo}
                onChange={(e) => setOrderTo(e.target.value)}
                title="结束日期"
              />
            </div>
          </div>

          {pageOrders.length === 0 ? (
            <div className="profile-empty">
              <strong>暂无订单</strong>
              <span>
                {formalOrders.length === 0
                  ? "充值后可在此查看正式 VIP 套餐订单"
                  : "当前筛选条件下没有匹配订单，试试调整筛选"}
              </span>
            </div>
          ) : (
            <>
              <div className="order-list">
                {pageOrders.map((o) => (
                  <div
                    key={o.id}
                    className="order-row order-row-click"
                    onClick={(e) => {
                      if (e.target.closest("button")) return;
                      setOrderDetail(o);
                    }}
                  >
                    <div className="order-main">
                      <strong>{o.package_name}</strong>
                      <span className="order-date">
                        {o.created_at ? o.created_at.slice(0, 16).replace("T", " ") : "—"}
                        {" · "}
                        {channelLabel(o.channel)}
                      </span>
                    </div>
                    <div className="order-meta">
                      <span className="order-amount">¥{o.amount}</span>
                      <span className={`order-status status-${o.status}`}>{statusLabel(o.status)}</span>
                      {o.status === "pending" && (
                        <div className="order-actions">
                          <button
                            type="button"
                            className="btn-primary"
                            disabled={!!paying}
                            onClick={() => continuePay(o.id)}
                          >
                            {paying === `order-${o.id}` ? "跳转中…" : "继续支付"}
                          </button>
                          <button type="button" className="logout-btn" onClick={() => cancelOrder(o.id)}>
                            取消
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
              {filteredOrders.length > ORDER_PAGE_SIZE ? (
                <div className="order-pager">
                  <span>
                    第 {orderPage} / {orderPages} 页
                  </span>
                  <div className="order-pager-btns">
                    <button
                      type="button"
                      className="logout-btn"
                      disabled={orderPage <= 1}
                      onClick={() => setOrderPage((p) => p - 1)}
                    >
                      上一页
                    </button>
                    <button
                      type="button"
                      className="logout-btn"
                      disabled={orderPage >= orderPages}
                      onClick={() => setOrderPage((p) => p + 1)}
                    >
                      下一页
                    </button>
                  </div>
                </div>
              ) : null}
            </>
          )}
        </div>

        <div className="profile-faq">
          <h3 className="panel-title">充值 FAQ</h3>
          <div className="faq-list">
            {FAQ_ITEMS.map((item, idx) => {
              const open = faqOpen === idx;
              return (
                <div key={item.q} className={`faq-item${open ? " open" : ""}`}>
                  <button type="button" className="faq-q" onClick={() => setFaqOpen(open ? null : idx)}>
                    <span>{item.q}</span>
                    <em>{open ? "收起" : "展开"}</em>
                  </button>
                  {open ? <p className="faq-a">{item.a}</p> : null}
                </div>
              );
            })}
          </div>
        </div>
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

      <ProfileModal
        open={Boolean(benefitDetail)}
        title={benefitDetail?.title || "权益说明"}
        onClose={() => setBenefitDetail(null)}
      >
        <p>{benefitDetail?.detail}</p>
      </ProfileModal>

      <ProfileModal
        open={Boolean(payToast)}
        title={payToast?.title || "提示"}
        onClose={() => setPayToast(null)}
        actions={
          <button type="button" className="btn-primary" onClick={() => setPayToast(null)}>
            知道了
          </button>
        }
      >
        <p className={payToast?.type === "err" ? "form-error" : "form-ok"} style={{ margin: 0 }}>
          {payToast?.message}
        </p>
      </ProfileModal>

      <ProfileModal
        open={Boolean(orderDetail)}
        title="订单详情"
        onClose={() => setOrderDetail(null)}
        actions={
          <>
            {orderDetail?.status === "pending" ? (
              <button
                type="button"
                className="btn-primary"
                disabled={!!paying}
                onClick={() => {
                  const id = orderDetail.id;
                  setOrderDetail(null);
                  continuePay(id);
                }}
              >
                继续支付
              </button>
            ) : null}
            <button type="button" className="logout-btn" onClick={() => setOrderDetail(null)}>
              关闭
            </button>
          </>
        }
      >
        {orderDetail ? (
          <dl className="order-detail-dl">
            <div>
              <dt>套餐</dt>
              <dd>{orderDetail.package_name}</dd>
            </div>
            <div>
              <dt>金额</dt>
              <dd>¥{orderDetail.amount}</dd>
            </div>
            <div>
              <dt>状态</dt>
              <dd>
                <span className={`order-status status-${orderDetail.status}`}>
                  {statusLabel(orderDetail.status)}
                </span>
              </dd>
            </div>
            <div>
              <dt>支付渠道</dt>
              <dd>{channelLabel(orderDetail.channel)}</dd>
            </div>
            <div>
              <dt>开通天数</dt>
              <dd>{orderDetail.days || "—"} 天</dd>
            </div>
            <div>
              <dt>下单时间</dt>
              <dd>
                {orderDetail.created_at
                  ? orderDetail.created_at.slice(0, 19).replace("T", " ")
                  : "—"}
              </dd>
            </div>
            <div>
              <dt>订单号</dt>
              <dd className="mono">{orderDetail.id}</dd>
            </div>
            <div>
              <dt>商户单号 / 交易流水</dt>
              <dd className="mono">{orderDetail.out_trade_no || "—"}</dd>
            </div>
            {orderDetail.remark ? (
              <div>
                <dt>备注</dt>
                <dd>{orderDetail.remark}</dd>
              </div>
            ) : null}
          </dl>
        ) : null}
      </ProfileModal>
    </div>
  );
}
