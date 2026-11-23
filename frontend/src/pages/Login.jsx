import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, setSession } from "../api";

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

  const onChange = (e) => {
    setForm({ ...form, [e.target.name]: e.target.value });
    setError("");
  };

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      if (mode === "login") {
        const res = await api.login({
          username: form.username,
          password: form.password,
        });
        setSession({
          user_id: res.data.user_id,
          username: res.data.username,
          nickname: res.data.nickname || res.data.username,
          is_vip: res.data.is_vip,
          is_admin: res.data.is_admin,
          vip_expire_at: res.data.vip_expire_at,
        });
        navigate("/");
      } else {
        const res = await api.register({
          username: form.username,
          email: form.email,
          password: form.password,
          nickname: form.nickname || form.username,
        });
        setSession({
          user_id: res.data.user_id,
          username: res.data.username,
          nickname: res.data.nickname || res.data.username,
          is_vip: res.data.is_vip,
          is_admin: res.data.is_admin,
          vip_expire_at: res.data.vip_expire_at,
        });
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
        <div className="hero" style={{ marginBottom: 24 }}>
          <div className="hero-logo">🤖</div>
          <h1>Apex AI</h1>
          <p>从熬夜加班到一键生成，你和高效办公只差一个 AI</p>
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
              />
            </div>
          )}
          <div className="form-field">
            <label>用户名</label>
            <input
              name="username"
              required
              placeholder="登录用户名"
              value={form.username}
              onChange={onChange}
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
              />
            </div>
          )}
          <div className="form-field">
            <label>密码</label>
            <input
              name="password"
              type="password"
              required
              placeholder="请输入密码"
              value={form.password}
              onChange={onChange}
            />
          </div>
          {error && <div className="form-error">{error}</div>}
          <button
            type="submit"
            className="btn-primary"
            style={{ width: "100%" }}
            disabled={loading}
          >
            {loading ? "请稍候…" : mode === "login" ? "登录" : "注册并进入"}
          </button>
        </form>

        <p className="login-hint">
          演示账号：用户名 xiaoyema / 密码 123456
          <br />
          登录后昵称显示为「小野马」，下方会附带 @xiaoyema
        </p>
      </div>
    </div>
  );
}
