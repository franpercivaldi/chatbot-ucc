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
