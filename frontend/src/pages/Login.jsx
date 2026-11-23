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
    vip_expire_at: data.vip_expire_at,
    access_token: data.access_token,
    token_type: data.token_type || "Bearer",
  });
}

export default function Login() {
  const navigate = useNavigate();
  const [mode, setMode] = useState("login");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState({
    username: "",
    email: "",
    password: "",
    nickname: "",
  });

  const strength = useMemo(() => passwordStrength(form.password), [form.password]);

  const onChange = (e) => {
    setForm({ ...form, [e.target.name]: e.target.value });
    setError("");
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
      } else {
        const res = await api.register({
          username: form.username.trim(),
          email: form.email.trim(),
          password: form.password,
          nickname: form.nickname.trim() || form.username.trim(),
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
          <span>失败限流</span>
        </div>

        <div className="login-tabs">
          <button
            type="button"
            className={mode === "login" ? "active" : ""}
            onClick={() => setMode("login")}
          >
            登录
          </button>
          <button
            type="button"
            className={mode === "register" ? "active" : ""}
            onClick={() => setMode("register")}
          >
            注册
          </button>
        </div>

        <form onSubmit={submit}>
          {mode === "register" && (
            <div className="form-field">
              <label>昵称</label>
              <input
                name="nickname"
                placeholder="显示名称"
                value={form.nickname}
                onChange={onChange}
                autoComplete="nickname"
              />
            </div>
          )}
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
          {mode === "register" && (
            <div className="form-field">
              <label>邮箱</label>
              <input
                name="email"
                type="email"
                required
                placeholder="name@example.com"
                value={form.email}
                onChange={onChange}
                autoComplete="email"
              />
            </div>
          )}
          <div className="form-field">
            <label>密码</label>
            <input
              name="password"
              type="password"
              required
              minLength={6}
              placeholder={mode === "register" ? "至少 6 位" : "请输入密码"}
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
          {error && <div className="form-error">{error}</div>}
          <button
            type="submit"
            className="btn-primary"
            style={{ width: "100%" }}
            disabled={loading}
          >
            {loading ? "请稍候…" : mode === "login" ? "安全登录" : "注册并进入"}
          </button>
        </form>

        <p className="login-hint">
          登录后签发 JWT，业务接口需携带令牌；密码仅以哈希形式存储。
        </p>
      </div>
    </div>
  );
}
