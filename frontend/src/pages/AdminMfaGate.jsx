import { useEffect, useState } from "react";
import { api } from "../api";

/** 管理操作前的邮箱二次验证（通过后约 30 分钟内有效） */
export default function AdminMfaGate({ children }) {
  const [loading, setLoading] = useState(true);
  const [mfaValid, setMfaValid] = useState(false);
  const [emailHint, setEmailHint] = useState("");
  const [code, setCode] = useState("");
  const [demoCode, setDemoCode] = useState("");
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const [sending, setSending] = useState(false);
  const [verifying, setVerifying] = useState(false);

  const refresh = async () => {
    setLoading(true);
    setError("");
    try {
      const res = await api.adminMfaStatus();
      const d = res.data || {};
      setMfaValid(Boolean(d.mfa_valid));
      setEmailHint(d.email || (d.email_bound ? "已绑定邮箱" : ""));
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

  const send = async () => {
    setSending(true);
    setError("");
    setInfo("");
    setDemoCode("");
    try {
      const res = await api.adminMfaSend();
      setInfo(res.msg || "验证码已发送，请查收邮箱（含垃圾箱）");
      if (res.data?.demo && res.data?.demo_code) {
        setDemoCode(res.data.demo_code);
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

  return (
    <div className="page-scroll" style={{ maxWidth: 480, margin: "40px auto", padding: 16 }}>
      <div className="card" style={{ padding: 24 }}>
        <h1 style={{ margin: "0 0 8px", fontSize: 20 }}>管理端二次验证</h1>
        <p style={{ color: "#636e72", margin: "0 0 16px", lineHeight: 1.5 }}>
          开通 VIP、看用户列表等敏感操作前，需要邮箱验证码确认。通过后约 30 分钟内有效。
        </p>
        {emailHint ? (
          <p style={{ marginBottom: 12 }}>
            账号绑定邮箱：<strong>{emailHint}</strong>
            {String(emailHint).includes("apex.ai") ? (
              <span style={{ display: "block", marginTop: 6, color: "#b7791f" }}>
                这是系统演示邮箱（不是你的私人邮箱），收不到信。点「获取验证码」后，验证码会直接显示在本页。
              </span>
            ) : null}
          </p>
        ) : (
          <p className="form-error" style={{ marginBottom: 12 }}>
            当前管理员账号未绑定邮箱，请先补全邮箱后再验证。
          </p>
        )}
        <form onSubmit={verify}>
          <div className="form-field">
            <label>验证码</label>
            <div className="sms-inline">
              <input
                value={code}
                onChange={(e) => setCode(e.target.value)}
                placeholder="6 位邮箱验证码"
                maxLength={6}
                inputMode="numeric"
                required
              />
              <button type="button" className="logout-btn" onClick={send} disabled={sending || !emailHint}>
                {sending ? "发送中…" : "获取验证码"}
              </button>
            </div>
          </div>
          {demoCode ? (
            <p className="form-ok" style={{ marginBottom: 8, fontSize: 16 }}>
              演示验证码（填这个）：<strong>{demoCode}</strong>
            </p>
          ) : null}
          {info ? <p className="form-ok" style={{ marginBottom: 8 }}>{info}</p> : null}
          {error ? <p className="form-error" style={{ marginBottom: 8 }}>{error}</p> : null}
          <button type="submit" className="btn-primary" style={{ width: "100%" }} disabled={verifying}>
            {verifying ? "验证中…" : "确认验证"}
          </button>
        </form>
      </div>
    </div>
  );
}
