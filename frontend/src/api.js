function resolveApiUrl(path) {
  if (import.meta.env.VITE_API_BASE) {
    return `${import.meta.env.VITE_API_BASE.replace(/\/$/, "")}${path}`;
  }
  if (typeof window === "undefined") return path;

  const { protocol, hostname, port } = window.location;
  const onAppServer =
    protocol.startsWith("http") &&
    (port === "8000" || (port === "" && hostname === "127.0.0.1"));

  if (onAppServer) return path;

  if (protocol === "file:" || port === "5173") {
    return `http://127.0.0.1:8000${path}`;
  }

  if (protocol === "https:") {
    return `http://127.0.0.1:8000${path}`;
  }

  return `http://127.0.0.1:8000${path}`;
}

/** Resolve /generated/... assets for download/preview across 5173 and 8000. */
export function resolveAssetUrl(path) {
  if (!path) return "";
  if (/^https?:\/\//i.test(path)) return path;
  return resolveApiUrl(path.startsWith("/") ? path : `/${path}`);
}

export function isWrongPreviewPage() {
  if (typeof window === "undefined") return false;
  const { protocol, port } = window.location;
  return protocol === "https:" || (port !== "" && port !== "8000" && port !== "5173");
}

async function request(path, options = {}) {
  const { timeoutMs = 30000, ...fetchOptions } = options;
  const url = resolveApiUrl(path);
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const res = await fetch(url, {
      headers: { "Content-Type": "application/json", ...fetchOptions.headers },
      signal: controller.signal,
      ...fetchOptions,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const detail = data.detail;
      const msg =
        typeof detail === "string"
          ? detail
          : Array.isArray(detail)
            ? detail.map((d) => d.msg || d).join("; ")
            : data.msg || "请求失败";
      throw new Error(msg);
    }
    return data;
  } catch (e) {
    if (e.name === "AbortError") {
      throw new Error("请求超时，请稍后重试");
    }
    if (e instanceof TypeError || e.message === "Failed to fetch") {
      throw new Error("NETWORK");
    }
    throw e;
  } finally {
    clearTimeout(timer);
  }
}

export const api = {
  health: async () => {
    try {
      return await request("/api/health", { timeoutMs: 5000 });
    } catch {
      return await request("/api/hot-topics", { timeoutMs: 5000 });
    }
  },
  register: (body) =>
    request("/api/register", { method: "POST", body: JSON.stringify(body) }),
  login: (body) =>
    request("/api/login", { method: "POST", body: JSON.stringify(body) }),
  profile: (userId) => request(`/api/users/${userId}/profile`),
  updateProfile: (body) =>
    request("/api/users/profile/update", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  hotTopics: () => request("/api/hot-topics"),
  tools: (params = {}) => {
    const q = new URLSearchParams(params).toString();
    return request(`/api/tools${q ? `?${q}` : ""}`);
  },
  agents: (params = {}) => {
    const q = new URLSearchParams(params).toString();
    return request(`/api/agents${q ? `?${q}` : ""}`);
  },
  conversations: (userId) => request(`/api/conversations?user_id=${userId}`),
  updateConversation: (id, body) =>
    request(`/api/conversations/${id}/update`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  deleteConversation: (id, userId) =>
    request(`/api/conversations/${id}/remove`, {
      method: "POST",
      body: JSON.stringify({ user_id: userId }),
    }),
  createConversation: (body) =>
    request("/api/conversations", { method: "POST", body: JSON.stringify(body) }),
  messages: (conversationId, userId) =>
    request(`/api/conversations/${conversationId}/messages?user_id=${userId}`),
  chat: (body) =>
    request("/api/chat", {
      method: "POST",
      body: JSON.stringify(body),
      timeoutMs: 180000,
    }),
  getTool: (id) => request(`/api/tools/${id}`),
  invokeTool: (id, body) =>
    request(`/api/tools/${id}/invoke`, {
      method: "POST",
      body: JSON.stringify(body),
      timeoutMs: 180000,
    }),
  generateMedia: (body) =>
    request("/api/media/generate", {
      method: "POST",
      body: JSON.stringify(body),
      timeoutMs: 180000,
    }),
  vipPackages: () => request("/api/vip/packages"),
  vipStatus: (userId) => request(`/api/vip/status?user_id=${userId}`),
  vipRecharge: (body) =>
    request("/api/vip/recharge", { method: "POST", body: JSON.stringify(body) }),
  vipOrderDetail: (orderId, userId) =>
    request(`/api/vip/orders/${orderId}?user_id=${userId}`),
  vipOrders: (userId) => request(`/api/vip/orders?user_id=${userId}`),
  vipCancelOrder: (orderId, userId) =>
    request(`/api/vip/orders/${orderId}/cancel`, {
      method: "POST",
      body: JSON.stringify({ user_id: userId }),
    }),
  vipContinuePay: (orderId, userId) =>
    request(`/api/vip/orders/${orderId}/pay`, {
      method: "POST",
      body: JSON.stringify({ user_id: userId }),
    }),
  adminUsers: (adminUserId) =>
    request(`/api/admin/users?admin_user_id=${adminUserId}`),
  adminGrantVip: (body) =>
    request("/api/admin/vip/grant", { method: "POST", body: JSON.stringify(body) }),
  adminRevokeVip: (body) =>
    request("/api/admin/vip/revoke", { method: "POST", body: JSON.stringify(body) }),
  adminRecharges: (adminUserId) =>
    request(`/api/admin/recharges?admin_user_id=${adminUserId}`),
};

export function getSession() {
  const raw = localStorage.getItem("apex_user");
  return raw ? JSON.parse(raw) : null;
}

export function setSession(user) {
  localStorage.setItem("apex_user", JSON.stringify(user));
}

export function clearSession() {
  localStorage.removeItem("apex_user");
}
