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
  const [mode, setMode] = useState("login");
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const [demoCode, setDemoCode] = useState("");
  const [loading, setLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [form, setForm] = useState({
    username: "",
    email: "",
    password: "",
    nickname: "",
    email_code: "",
  });

  const strength = useMemo(() => passwordStrength(form.password), [form.password]);

  const onChange = (e) => {
    setForm({ ...form, [e.target.name]: e.target.value });
    setError("");
  };

  const sceneForMode =
    mode === "email" ? "email_login" : mode === "reset" ? "reset_password" : "register";

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
      const res = await api.sendEmailCode({ email, scene: sceneForMode });
      setInfo(`验证码已发到 ${res.data?.email || "邮箱"}`);
      if (res.data?.demo_code) setDemoCode(res.data.demo_code);
    } catch (err) {
      setError(err.message);
    } finally {
      setSending(false);
    }
  };

  const submit = async (e) => {
    e.preventDefault();
    if (mode === "register") {
      if (form.username.trim().length < 3) {
        setError("用户名至少 3 位");
        return;
      }
      if (form.password.length < 6) {
        setError("密码至少 6 位");
        return;
      }
    }
    if (mode === "reset" && form.password.length < 6) {
      setError("新密码至少 6 位");
      return;
    }
    setLoading(true);
    setError("");
    try {
      if (mode === "login") {
        const res = await api.login({
          username: form.username.trim(),
          password: form.password,
        });
        saveAuthSession(res.data);
        navigate("/");
      } else if (mode === "email") {
        const res = await api.loginEmail({
          email: form.email.trim(),
          email_code: form.email_code.trim(),
        });
        saveAuthSession(res.data);
        navigate("/");
      } else if (mode === "reset") {
        await api.resetPassword({
          email: form.email.trim(),
          email_code: form.email_code.trim(),
          new_password: form.password,
        });
        setInfo("密码已重置，请用新密码登录");
        setMode("login");
        setForm((f) => ({ ...f, email_code: "", password: "" }));
        setDemoCode("");
      } else {
        const res = await api.register({
          username: form.username.trim(),
          email: form.email.trim(),
          password: form.password,
          nickname: form.nickname.trim() || form.username.trim(),
          email_code: form.email_code.trim(),
        });
        saveAuthSession(res.data);
        navigate("/");
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-page">
      <div className="login-card card">
        <div className="hero" style={{ marginBottom: 20 }}>
          <div className="hero-logo">🤖</div>
          <h1>Apex AI</h1>
          <p>从熬夜加班到一键生成，你和高效办公只差一个 AI</p>
        </div>

        <div className="login-security">
          <span>bcrypt 密码哈希</span>
          <span>JWT 鉴权</span>
          <span>邮箱验证码</span>
          <span>管理员二次验证</span>
        </div>

        <div className="login-tabs">
          <button type="button" className={mode === "login" ? "active" : ""} onClick={() => setMode("login")}>
            密码登录
          </button>
          <button type="button" className={mode === "email" ? "active" : ""} onClick={() => setMode("email")}>
            邮箱登录
          </button>
          <button type="button" className={mode === "register" ? "active" : ""} onClick={() => setMode("register")}>
            注册
          </button>
          <button type="button" className={mode === "reset" ? "active" : ""} onClick={() => setMode("reset")}>
            找回密码
          </button>
        </div>

        <form onSubmit={submit}>
          {mode === "register" && (
            <div className="form-field">
              <label>昵称</label>
              <input name="nickname" placeholder="显示名称" value={form.nickname} onChange={onChange} autoComplete="nickname" />
            </div>
          )}
          {(mode === "login" || mode === "register") && (
            <div className="form-field">
              <label>用户名</label>
              <input
                name="username"
                required
                minLength={mode === "register" ? 3 : 1}
                placeholder={mode === "register" ? "3～32 位登录名" : "登录用户名"}
                value={form.username}
                onChange={onChange}
                autoComplete="username"
              />
            </div>
          )}
          {mode !== "login" && (
            <div className="form-field">
              <label>邮箱</label>
              <div className="sms-inline">
                <input
                  name="email"
                  type="email"
                  required
                  placeholder="name@qq.com"
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
          {mode !== "login" && (
            <div className="form-field">
              <label>邮箱验证码</label>
              <input
                name="email_code"
                required
                inputMode="numeric"
                maxLength={6}
                placeholder="6 位数字"
                value={form.email_code}
                onChange={onChange}
              />
            </div>
          )}
          {mode !== "email" && (
            <div className="form-field">
              <label>{mode === "reset" ? "新密码" : "密码"}</label>
              <input
                name="password"
                type="password"
                required
                minLength={6}
                placeholder={mode === "login" ? "请输入密码" : "至少 6 位"}
                value={form.password}
                onChange={onChange}
                autoComplete={mode === "login" ? "current-password" : "new-password"}
              />
              {mode === "register" && form.password && (
                <div className={`pwd-strength level-${strength.level}`}>
                  <div className="pwd-strength-bar" />
                  <span>强度：{strength.label}</span>
                </div>
              )}
            </div>
          )}
          {demoCode && (
            <div className="demo-code">
              演示验证码：{demoCode}（未配 SMTP 时显示；配好 QQ/163 授权码后会发到邮箱）
            </div>
          )}
          {info && <div className="form-ok">{info}</div>}
          {error && <div className="form-error">{error}</div>}
          <button type="submit" className="btn-primary" style={{ width: "100%" }} disabled={loading}>
            {loading
              ? "请稍候…"
              : mode === "login"
                ? "安全登录"
                : mode === "email"
                  ? "邮箱验证码登录"
                  : mode === "reset"
                    ? "重置密码"
                    : "注册并进入"}
          </button>
        </form>

        <p className="login-hint">
          验证码发到邮箱（个人 QQ/163 SMTP 即可）。管理员请用账号密码登录，进入后台再做邮箱二次验证。
        </p>
      </div>
    </div>
  );
}
