import { useEffect, useState } from "react";
import { api, getSession, setSession } from "../api";

/** 管理操作前的邮箱二次验证（通过后约 30 分钟内有效） */
export default function AdminMfaGate({ children }) {
  const session = getSession();
  const [loading, setLoading] = useState(true);
  const [mfaValid, setMfaValid] = useState(false);
  const [emailHint, setEmailHint] = useState("");
  const [emailBound, setEmailBound] = useState(false);
  const [bindEmail, setBindEmail] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const [sending, setSending] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [savingEmail, setSavingEmail] = useState(false);

  const refresh = async () => {
    setLoading(true);
    setError("");
    try {
      const res = await api.adminMfaStatus();
      const d = res.data || {};
      setMfaValid(Boolean(d.mfa_valid));
      setEmailBound(Boolean(d.email_bound));
      setEmailHint(d.email || "");
    } catch (e) {
      setError(e.message || "无法检查二次验证状态");
      setMfaValid(false);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
  }, []);

  const saveEmail = async () => {
    const email = bindEmail.trim();
    if (!email.includes("@")) {
      setError("请填写真实邮箱");
      return;
    }
    setSavingEmail(true);
    setError("");
    setInfo("");
    try {
      const res = await api.updateProfile({
        user_id: session.user_id,
        email,
      });
      setSession({ ...session, email: res.data?.email || email });
      setInfo("邮箱已更新，请点击获取验证码，到该邮箱查收");
      setBindEmail("");
      await refresh();
    } catch (e) {
      setError(e.message || "更新邮箱失败（若提示已被占用，请换一个邮箱）");
    } finally {
      setSavingEmail(false);
    }
  };

  const send = async () => {
    setSending(true);
    setError("");
    setInfo("");
    try {
      const res = await api.adminMfaSend();
      if (res.data?.demo && res.data?.demo_code) {
        setInfo(`当前仍是演示发码。验证码：${res.data.demo_code}（请先把管理员邮箱改成你的真实邮箱）`);
      } else {
        setInfo(res.msg || "验证码已发送到你的邮箱，请查收（含垃圾箱）");
      }
    } catch (e) {
      setError(e.message || "发送失败");
    } finally {
      setSending(false);
    }
  };

  const verify = async (e) => {
    e.preventDefault();
    setVerifying(true);
    setError("");
    try {
      await api.adminMfaVerify({ sms_code: code.trim() });
      setInfo("二次验证通过，30 分钟内可操作后台");
      setMfaValid(true);
      setCode("");
    } catch (err) {
      setError(err.message || "验证失败");
    } finally {
      setVerifying(false);
    }
  };

  if (loading) {
    return <p style={{ padding: 24, color: "#636e72" }}>检查二次验证状态…</p>;
  }

  if (mfaValid) {
    return children;
  }

  const needBindReal =
    !emailBound || String(emailHint).includes("apex.ai") || !emailHint;

  return (
    <div className="page-scroll" style={{ maxWidth: 520, margin: "40px auto", padding: 16 }}>
      <div className="card" style={{ padding: 24 }}>
        <h1 style={{ margin: "0 0 8px", fontSize: 20 }}>管理端二次验证</h1>
        <p style={{ color: "#636e72", margin: "0 0 16px", lineHeight: 1.5 }}>
          开通 VIP、看用户列表等操作前，需向<strong>管理员账号绑定的真实邮箱</strong>发送验证码。
          通过后约 30 分钟内有效。
        </p>
        <p style={{ color: "#636e72", margin: "0 0 16px", fontSize: 13, lineHeight: 1.5 }}>
          说明：系统里<strong>一个邮箱只能绑定一个账号</strong>。管理员用你的邮箱收二次验证；
          普通用户请用另一个邮箱注册，或使用账号密码登录。
        </p>

        {emailHint ? (
          <p style={{ marginBottom: 12 }}>
            当前绑定：<strong>{emailHint}</strong>
          </p>
        ) : null}

        {needBindReal ? (
          <div className="form-field" style={{ marginBottom: 16 }}>
            <label>改绑真实邮箱（必填）</label>
            <div className="sms-inline">
              <input
                type="email"
                value={bindEmail}
                onChange={(e) => setBindEmail(e.target.value)}
                placeholder="例如你的 QQ 邮箱"
              />
              <button type="button" className="logout-btn" onClick={saveEmail} disabled={savingEmail}>
                {savingEmail ? "保存中…" : "保存邮箱"}
              </button>
            </div>
          </div>
        ) : (
          <div className="form-field" style={{ marginBottom: 12 }}>
            <label>更换邮箱（可选）</label>
            <div className="sms-inline">
              <input
                type="email"
                value={bindEmail}
                onChange={(e) => setBindEmail(e.target.value)}
                placeholder="换绑其他真实邮箱"
              />
              <button type="button" className="logout-btn" onClick={saveEmail} disabled={savingEmail || !bindEmail.trim()}>
                {savingEmail ? "保存中…" : "更新"}
              </button>
            </div>
          </div>
        )}

        <form onSubmit={verify}>
          <div className="form-field">
            <label>验证码</label>
            <div className="sms-inline">
              <input
                value={code}
                onChange={(e) => setCode(e.target.value)}
                placeholder="邮箱里收到的 6 位验证码"
                maxLength={6}
                inputMode="numeric"
                required
              />
              <button
                type="button"
                className="logout-btn"
                onClick={send}
                disabled={sending || needBindReal}
              >
                {sending ? "发送中…" : "获取验证码"}
              </button>
            </div>
          </div>
          {needBindReal ? (
            <p className="form-error" style={{ marginBottom: 8 }}>
              请先保存真实邮箱，再获取验证码（演示邮箱收不到信）。
            </p>
          ) : null}
          {info ? <p className="form-ok" style={{ marginBottom: 8 }}>{info}</p> : null}
          {error ? <p className="form-error" style={{ marginBottom: 8 }}>{error}</p> : null}
          <button
            type="submit"
            className="btn-primary"
            style={{ width: "100%" }}
            disabled={verifying || needBindReal}
          >
            {verifying ? "验证中…" : "确认验证"}
          </button>
        </form>
      </div>
    </div>
  );
}
