const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

export async function chat(
  message,
  meta = null,
  { timeoutMs = 30000, botId, sessionId, orgUnits, debug } = {}
) {
  const ctrl = new AbortController();
  const to = setTimeout(() => ctrl.abort(), timeoutMs);

  try {
    const headers = { "Content-Type": "application/json" };

  // DEFAULT de orgUnits: si no vienen explícitas, elegir según botId.
  // - Para 'interno-academico' usar solo 'general' (como en tu curl de prueba)
  // - Para otros bots usar 'general' y 'aranceles-beca'
  const defaultForBot = botId === "interno-academico" ? ["general"] : ["general", "aranceles-beca"];
  const finalOrgUnits = Array.isArray(orgUnits) && orgUnits.length ? orgUnits : defaultForBot;
    headers["X-Org-Units"] = finalOrgUnits.join(",");

    const body = {
      message,
      meta,
      ...(botId ? { bot_id: botId } : {}),
      ...(sessionId ? { session_id: sessionId } : {}),
      ...(typeof debug === "boolean" ? { debug } : {}),
    };

  // Debug: mostrar request que se envía para comparar con curl
  console.log("POST", `${API_URL}/chat/`, { headers, body });
    const res = await fetch(`${API_URL}/chat/`, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
      signal: ctrl.signal,
    });

    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(`HTTP ${res.status}: ${text || res.statusText}`);
    }
    return await res.json();
  } finally {
    clearTimeout(to);
  }
}

export async function* chatStream(
  message,
  meta = null,
  { timeoutMs = 30000, botId, sessionId, orgUnits, debug } = {}
) {
  const ctrl = new AbortController();
  const to = setTimeout(() => ctrl.abort(), timeoutMs);

  try {
    const headers = { "Content-Type": "application/json" };

    const defaultForBot = botId === "interno-academico" ? ["general"] : ["general", "aranceles-beca"];
    const finalOrgUnits = Array.isArray(orgUnits) && orgUnits.length ? orgUnits : defaultForBot;
    headers["X-Org-Units"] = finalOrgUnits.join(",");

    const body = {
      message,
      meta,
      ...(botId ? { bot_id: botId } : {}),
      ...(sessionId ? { session_id: sessionId } : {}),
      ...(typeof debug === "boolean" ? { debug } : {}),
    };

    console.log("POST", `${API_URL}/chat/stream`, { headers, body });

    const res = await fetch(`${API_URL}/chat/stream`, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
      signal: ctrl.signal,
    });

    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(`HTTP ${res.status}: ${text || res.statusText}`);
    }

    const reader = res.body?.getReader();
    if (!reader) throw new Error("Streaming no soportado por el navegador");

    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const events = buffer.split("\n\n");
      buffer = events.pop() || "";

      for (const raw of events) {
        const dataLine = raw
          .split("\n")
          .filter((l) => l.startsWith("data:"))
          .map((l) => l.replace(/^data:\s*/, ""))
          .join("\n");
        if (!dataLine) continue;
        try {
          const payload = JSON.parse(dataLine);
          yield payload;
        } catch (e) {
          console.warn("stream parse error", e, dataLine);
        }
      }
    }

    if (buffer.trim()) {
      const dataLine = buffer
        .split("\n")
        .filter((l) => l.startsWith("data:"))
        .map((l) => l.replace(/^data:\s*/, ""))
        .join("\n");
      if (dataLine) {
        try {
          yield JSON.parse(dataLine);
        } catch (e) {
          console.warn("stream parse error (tail)", e, dataLine);
        }
      }
    }
  } finally {
    clearTimeout(to);
  }
}

// Helpers genéricos (si los usás en otras pantallas)
async function req(path, { method = "GET", body, headers = {}, orgUnits, timeoutMs = 30000 } = {}) {
  const ctrl = new AbortController();
  const to = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
  const h = { "Content-Type": "application/json", ...headers };
  // si no se pasan orgUnits explícitos, añadimos el par por defecto
  const finalReqOrg = Array.isArray(orgUnits) && orgUnits.length ? orgUnits : ["general", "aranceles-beca"];
  h["X-Org-Units"] = finalReqOrg.join(",");
  // Debug: mostrar request genérico
  console.log(method, `${API_URL}${path}`, { headers: h, body });
    const res = await fetch(`${API_URL}${path}`, {
      method,
      headers: h,
      body: body ? JSON.stringify(body) : undefined,
      signal: ctrl.signal,
    });
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(`HTTP ${res.status}: ${text || res.statusText}`);
    }
    return await res.json();
  } finally {
    clearTimeout(to);
  }
}

export function apiGet(path, opts = {}) { return req(path, { method: "GET", ...opts }); }
export function apiPost(path, body, opts = {}) { return req(path, { method: "POST", body, ...opts }); }

export function getToken() { return localStorage.getItem("adm_token") || ""; }
export function setToken(token) { token ? localStorage.setItem("adm_token", token) : localStorage.removeItem("adm_token"); }
