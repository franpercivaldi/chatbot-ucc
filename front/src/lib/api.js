const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

export async function chat(message, meta = null, { timeoutMs = 30000 } = {}) {
  const ctrl = new AbortController();
  const to = setTimeout(() => ctrl.abort(), timeoutMs);

  try {
    const res = await fetch(`${API_URL}/chat/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, meta }),
      signal: ctrl.signal,
    });

    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(`HTTP ${res.status}: ${text || res.statusText}`);
    }
    return await res.json(); // { answer, sources }
  } finally {
    clearTimeout(to);
  }
}

export function getToken() {
  return localStorage.getItem("adm_token") || "";
}

export function setToken(token) {
  if (token) localStorage.setItem("adm_token", token);
  else localStorage.removeItem("adm_token");
}

export async function apiGet(path) {
  const res = await fetch(`${API_URL}${path}`, {
    headers: {
      "Content-Type": "application/json",
      "Authorization": getToken() ? `Bearer ${getToken()}` : undefined,
    },
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function apiPost(path, body) {
  const res = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Authorization": getToken() ? `Bearer ${getToken()}` : undefined,
    },
    body: JSON.stringify(body || {}),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
