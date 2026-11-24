import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, setSession } from "../api";

function passwordStrength(pwd) {
  if (!pwd) return { level: 0, label: "" };
  let score = 0;
  if (pwd.length >= 6) score += 1;
  if (pwd.length >= 10) score += 1;
  if (/[A-Za-z]/.test(pwd) && /\d/.test(pwd)) score += 1;
  if (/[^A-Za-z0-9]/.test(pwd)) score += 1;
  const labels = ["", "弱", "中", "较强", "强"];
  return { level: score, label: labels[score] || "" };
}

function saveAuthSession(data) {
  setSession({
    user_id: data.user_id,
    username: data.username,
    nickname: data.nickname || data.username,
    email: data.email,
    is_vip: data.is_vip,
    is_admin: data.is_admin,
    phone: data.phone || "",
    vip_expire_at: data.vip_expire_at,
    access_token: data.access_token,
    token_type: data.token_type || "Bearer",
  });
}

export default function Login() {
  const navigate = useNavigate();
  // 主切换：登录 | 注册；登录内再分密码 / 邮箱验证码；找回为附属页
  const [panel, setPanel] = useState("login"); // login | register | reset
  const [loginWay, setLoginWay] = useState("password"); // password | email
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const [demoCode, setDemoCode] = useState("");
  const [loading, setLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [form, setForm] = useState({
    username: "",
    email: "",
    password: "",
    email_code: "",
  });

  const strength = useMemo(() => passwordStrength(form.password), [form.password]);
  const needCode = panel === "register" || panel === "reset" || loginWay === "email";

  const switchPanel = (next) => {
    setPanel(next);
    setError("");
    setInfo("");
    setDemoCode("");
  };

  const onChange = (e) => {
    setForm({ ...form, [e.target.name]: e.target.value });
    setError("");
  };

  const codeScene =
    panel === "reset" ? "reset_password" : panel === "register" ? "register" : "email_login";

  const sendCode = async () => {
    setError("");
    setInfo("");
    setDemoCode("");
    const email = form.email.trim();
    if (!email.includes("@")) {
      setError("请填写邮箱");
      return;
    }
    setSending(true);
    try {
      const res = await api.sendEmailCode({ email, scene: codeScene });
      setInfo(`验证码已发送至 ${res.data?.email || "邮箱"}，请查收（含垃圾箱）`);
      // 仅演示通道才回显；正式 SMTP 不在页面展示验证码
      if (res.data?.demo && res.data?.demo_code) setDemoCode(res.data.demo_code);
    } catch (err) {
      setError(err.message);
    } finally {
      setSending(false);
    }
  };

  const submit = async (e) => {
    e.preventDefault();
    if (panel === "register") {
      if (form.username.trim().length < 3) {
        setError("用户名至少 3 位");
        return;
      }
      if (form.password.length < 6) {
        setError("密码至少 6 位");
        return;
      }
    }
    if (panel === "reset" && form.password.length < 6) {
      setError("新密码至少 6 位");
      return;
    }
    setLoading(true);
    setError("");
    try {
      if (panel === "login" && loginWay === "password") {
        const res = await api.login({
          username: form.username.trim(),
          password: form.password,
        });
        saveAuthSession(res.data);
        navigate("/");
        return;
      }
      if (panel === "login" && loginWay === "email") {
        const res = await api.loginEmail({
          email: form.email.trim(),
          email_code: form.email_code.trim(),
        });
        saveAuthSession(res.data);
        navigate("/");
        return;
      }
      if (panel === "reset") {
        await api.resetPassword({
          email: form.email.trim(),
          email_code: form.email_code.trim(),
          new_password: form.password,
        });
        setInfo("密码已重置，请使用新密码登录");
        setLoginWay("password");
        switchPanel("login");
        setForm((f) => ({ ...f, email_code: "", password: "" }));
        return;
      }
      const res = await api.register({
        username: form.username.trim(),
        email: form.email.trim(),
        password: form.password,
        nickname: form.username.trim(),
        email_code: form.email_code.trim(),
      });
      saveAuthSession(res.data);
      navigate("/");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const title =
    panel === "register" ? "注册账号" : panel === "reset" ? "重置密码" : "登录 Apex AI";

  return (
    <div className="login-page">
      <div className="login-card card">
        <div className="hero" style={{ marginBottom: 20 }}>
          <div className="hero-logo">🤖</div>
          <h1>Apex AI</h1>
          <p>{title}</p>
        </div>

        {panel !== "reset" && (
          <div className="login-tabs">
            <button
              type="button"
              className={panel === "login" ? "active" : ""}
              onClick={() => switchPanel("login")}
            >
              登录
            </button>
            <button
              type="button"
              className={panel === "register" ? "active" : ""}
              onClick={() => switchPanel("register")}
            >
              注册
            </button>
          </div>
        )}

        {panel === "login" && (
          <div className="login-way">
            <button
              type="button"
              className={loginWay === "password" ? "active" : ""}
              onClick={() => {
                setLoginWay("password");
                setDemoCode("");
                setError("");
              }}
            >
              账号密码
            </button>
            <button
              type="button"
              className={loginWay === "email" ? "active" : ""}
              onClick={() => {
                setLoginWay("email");
                setDemoCode("");
                setError("");
              }}
            >
              邮箱验证码
            </button>
          </div>
        )}

        <form onSubmit={submit}>
          {(panel === "register" || (panel === "login" && loginWay === "password")) && (
            <div className="form-field">
              <label>用户名</label>
              <input
                name="username"
                required
                minLength={panel === "register" ? 3 : 1}
                placeholder={panel === "register" ? "3～32 位，用于登录" : "请输入用户名"}
                value={form.username}
                onChange={onChange}
                autoComplete="username"
              />
            </div>
          )}

          {needCode && (
            <div className="form-field">
              <label>邮箱</label>
              <div className="sms-inline">
                <input
                  name="email"
                  type="email"
                  required
                  placeholder="用于接收验证码"
                  value={form.email}
                  onChange={onChange}
                  autoComplete="email"
                />
                <button type="button" className="logout-btn" onClick={sendCode} disabled={sending}>
                  {sending ? "发送中…" : "获取验证码"}
                </button>
              </div>
            </div>
          )}

          {needCode && (
            <div className="form-field">
              <label>验证码</label>
              <input
                name="email_code"
                required
                inputMode="numeric"
                maxLength={6}
                placeholder="6 位邮箱验证码"
                value={form.email_code}
                onChange={onChange}
              />
            </div>
          )}

          {(panel === "register" ||
            panel === "reset" ||
            (panel === "login" && loginWay === "password")) && (
            <div className="form-field">
              <label>{panel === "reset" ? "新密码" : "密码"}</label>
              <input
                name="password"
                type="password"
                required
                minLength={6}
                placeholder={panel === "login" ? "请输入密码" : "至少 6 位"}
                value={form.password}
                onChange={onChange}
                autoComplete={panel === "login" ? "current-password" : "new-password"}
              />
              {panel === "register" && form.password && (
                <div className={`pwd-strength level-${strength.level}`}>
                  <div className="pwd-strength-bar" />
                  <span>强度：{strength.label}</span>
                </div>
              )}
            </div>
          )}

          {panel === "login" && loginWay === "password" && (
            <div className="login-links">
              <button type="button" className="linkish" onClick={() => switchPanel("reset")}>
                忘记密码？
              </button>
            </div>
          )}

          {demoCode && (
            <div className="demo-code">当前为演示通道，验证码：{demoCode}</div>
          )}
          {info && <div className="form-ok">{info}</div>}
          {error && <div className="form-error">{error}</div>}

          <button type="submit" className="btn-primary" style={{ width: "100%" }} disabled={loading}>
            {loading
              ? "请稍候…"
              : panel === "register"
                ? "注册并进入"
                : panel === "reset"
                  ? "确认重置"
                  : loginWay === "email"
                    ? "验证码登录"
                    : "登录"}
          </button>

          {panel === "reset" && (
            <button
              type="button"
              className="logout-btn"
              style={{ width: "100%", marginTop: 10 }}
              onClick={() => {
                setLoginWay("password");
                switchPanel("login");
              }}
            >
              返回登录
            </button>
          )}
        </form>

        <p className="login-hint">
          验证码发送至用户邮箱。管理员请用账号密码登录，进入后台后再做邮箱二次验证。
        </p>
      </div>
    </div>
  );
}
