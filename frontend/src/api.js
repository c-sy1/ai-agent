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

function authHeaders() {
  const session = getSession();
  const token = session?.access_token || session?.token;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function request(path, options = {}) {
  const { timeoutMs = 30000, ...fetchOptions } = options;
  const url = resolveApiUrl(path);
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const res = await fetch(url, {
      ...fetchOptions,
      headers: {
        "Content-Type": "application/json",
        ...authHeaders(),
        ...fetchOptions.headers,
      },
      signal: controller.signal,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      if (res.status === 401 && !path.startsWith("/api/login") && !path.startsWith("/api/register")) {
        clearSession();
      }
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
  loginPhone: (body) =>
    request("/api/login/phone", { method: "POST", body: JSON.stringify(body) }),
  loginEmail: (body) =>
    request("/api/login/email", { method: "POST", body: JSON.stringify(body) }),
  sendSms: (body) =>
    request("/api/sms/send", { method: "POST", body: JSON.stringify(body) }),
  sendEmailCode: (body) =>
    request("/api/email/send", { method: "POST", body: JSON.stringify(body) }),
  resetPassword: (body) =>
    request("/api/password/reset", { method: "POST", body: JSON.stringify(body) }),
  bindPhone: (body) =>
    request("/api/users/phone/bind", { method: "POST", body: JSON.stringify(body) }),
  mySms: () => request("/api/sms/mine"),
  adminMfaStatus: () => request("/api/admin/mfa/status"),
  adminMfaSend: () => request("/api/admin/mfa/send", { method: "POST", body: "{}" }),
  adminMfaVerify: (body) =>
    request("/api/admin/mfa/verify", { method: "POST", body: JSON.stringify(body) }),
  adminDisableUser: (body) =>
    request("/api/admin/users/disable", { method: "POST", body: JSON.stringify(body) }),
  adminResetPassword: (body) =>
    request("/api/admin/users/reset-password", { method: "POST", body: JSON.stringify(body) }),
  adminSetQuota: (body) =>
    request("/api/admin/users/quota", { method: "POST", body: JSON.stringify(body) }),
  adminApproveOrder: (body) =>
    request("/api/admin/orders/approve", { method: "POST", body: JSON.stringify(body) }),
  adminSms: () => request("/api/admin/sms"),
  profile: (userId) => request(`/api/users/${userId}/profile`),
  updateProfile: (body) =>
    request("/api/users/profile/update", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  hotTopics: () => request("/api/hot-topics"),
  works: (params = {}) => {
    const q = new URLSearchParams(params).toString();
    return request(`/api/works${q ? `?${q}` : ""}`);
  },
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
  mapConfig: () => request("/api/map/config"),
  mapPlaces: () => request("/api/map/places"),
  mapGeocode: (place) =>
    request("/api/map/geocode", {
      method: "POST",
      body: JSON.stringify({ place }),
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
  vipCouponsMine: () => request("/api/vip/coupons/mine"),
  vipCouponClaim: (code) =>
    request("/api/vip/coupons/claim", {
      method: "POST",
      body: JSON.stringify({ code }),
    }),
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
  vipContinuePay: (orderId, userId, smsCode = "") =>
    request(`/api/vip/orders/${orderId}/pay`, {
      method: "POST",
      body: JSON.stringify({ user_id: userId, sms_code: smsCode }),
    }),
  adminUsers: (adminUserId) =>
    request(`/api/admin/users?admin_user_id=${adminUserId}`),
  adminUserDetail: (userId) => request(`/api/admin/users/${userId}`),
  adminGrantVip: (body) =>
    request("/api/admin/vip/grant", { method: "POST", body: JSON.stringify(body) }),
  adminGrantVipBatch: (body) =>
    request("/api/admin/vip/grant-batch", { method: "POST", body: JSON.stringify(body) }),
  adminRevokeVip: (body) =>
    request("/api/admin/vip/revoke", { method: "POST", body: JSON.stringify(body) }),
  adminRecharges: (adminUserId) =>
    request(`/api/admin/recharges?admin_user_id=${adminUserId}`),
  adminOpLogs: (limit = 100) => request(`/api/admin/op-logs?limit=${limit}`),
  submitFeedback: (body) =>
    request("/api/feedback", { method: "POST", body: JSON.stringify(body) }),
  adminFeedback: () => request("/api/admin/feedback"),
  adminFeedbackUpdate: (id, body) =>
    request(`/api/admin/feedback/${id}/update`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  adminFeedbackBatch: (body) =>
    request("/api/admin/feedback/batch", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  adminFeedbackContext: (id) => request(`/api/admin/feedback/${id}/context`),
  supportCategories: () => request("/api/support/categories"),
  supportCreate: (body) =>
    request("/api/support/tickets", { method: "POST", body: JSON.stringify(body) }),
  supportMine: () => request("/api/support/tickets/mine"),
  adminSupportTickets: (status = "") =>
    request(`/api/admin/support/tickets${status ? `?status=${encodeURIComponent(status)}` : ""}`),
  adminSupportUpdate: (id, body) =>
    request(`/api/admin/support/tickets/${id}/update`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  adminCouponTemplates: () => request("/api/admin/coupons/templates"),
  adminGrantCoupon: (body) =>
    request("/api/admin/coupons/grant", { method: "POST", body: JSON.stringify(body) }),
  knowledgeCategories: () => request("/api/knowledge/categories"),
  knowledgeDocs: (category) =>
    request(`/api/knowledge/docs${category ? `?category=${encodeURIComponent(category)}` : ""}`),
  knowledgeCreate: (body) =>
    request("/api/knowledge/docs", { method: "POST", body: JSON.stringify(body) }),
  knowledgeRemove: (id) =>
    request(`/api/knowledge/docs/${id}/remove`, { method: "POST", body: "{}" }),
};

/** 用户端 / 管理端分两套会话，避免两个标签页互相顶号 */
const USER_SESSION_KEY = "apex_user_session";
const ADMIN_SESSION_KEY = "apex_admin_session";
const LEGACY_SESSION_KEY = "apex_user";

function isAdminPortalPath() {
  if (typeof window === "undefined") return false;
  return window.location.pathname.startsWith("/admin");
}

function sessionStorageKey() {
  return isAdminPortalPath() ? ADMIN_SESSION_KEY : USER_SESSION_KEY;
}

function readJson(key) {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function getSession() {
  const key = sessionStorageKey();
  let data = readJson(key);
  if (data) return data;

  // 兼容旧版单一 apex_user，按角色拆到对应门户
  const legacy = readJson(LEGACY_SESSION_KEY);
  if (!legacy) return null;
  if (isAdminPortalPath() && legacy.is_admin) {
    localStorage.setItem(ADMIN_SESSION_KEY, JSON.stringify(legacy));
    return legacy;
  }
  if (!isAdminPortalPath() && !legacy.is_admin) {
    localStorage.setItem(USER_SESSION_KEY, JSON.stringify(legacy));
    return legacy;
  }
  return null;
}

export function setSession(user) {
  localStorage.setItem(sessionStorageKey(), JSON.stringify(user));
}

export function clearSession() {
  localStorage.removeItem(sessionStorageKey());
  // 顺带清掉旧 key，避免下次又串号
  if (!isAdminPortalPath()) {
    const legacy = readJson(LEGACY_SESSION_KEY);
    if (legacy && !legacy.is_admin) localStorage.removeItem(LEGACY_SESSION_KEY);
  } else {
    const legacy = readJson(LEGACY_SESSION_KEY);
    if (legacy && legacy.is_admin) localStorage.removeItem(LEGACY_SESSION_KEY);
  }
}
