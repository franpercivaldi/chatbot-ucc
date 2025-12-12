import { useMemo, useState } from "react";
import ChatList from "./components/chat/ChatList";
import ChatInput from "./components/chat/ChatInput";
import { chatStream } from "./lib/api";

export default function Chat() {
  const [messages, setMessages] = useState([]);
  // Cambiamos el bot por defecto a 'interno-academico' para que el frontend
  // haga requests equivalentes a tu curl de pruebas (usa X-Org-Units: general)
  const [botId, setBotId] = useState("public-admisiones");

  const sessionId = useMemo(
    () =>
      globalThis.crypto?.randomUUID?.() ??
      `sess-${Date.now()}-${Math.random().toString(36).slice(2)}`,
    []
  );

  const genId = () =>
    globalThis.crypto?.randomUUID?.() ?? String(Date.now() + Math.random());

  const handleSend = async (text) => {
    const userMsg = { id: genId(), role: "user", text };
    const asstId = genId();
    setMessages((prev) => [
      ...prev,
      userMsg,
      { id: asstId, role: "assistant", text: "pensando…", sources: [], pending: true },
    ]);

    try {
      const meta = null;
      let acc = "";
      let gotFirstToken = false;

      for await (const evt of chatStream(text, meta, {
        botId,
        sessionId,
        debug: true,
      })) {
        if (evt.event === "token") {
          acc += evt.text || "";
          const snap = acc || "…";
          if (!gotFirstToken) {
            gotFirstToken = true;
          }
          setMessages((prev) => prev.map((m) => (
            m.id === asstId ? { ...m, text: snap, pending: false } : m
          )));
        } else if (evt.event === "end") {
          const finalText = evt.answer || acc || "No pude generar una respuesta.";
          const sources = Array.isArray(evt.sources) ? evt.sources : [];
          setMessages((prev) => prev.map((m) => (
            m.id === asstId ? { ...m, text: finalText, sources, pending: false } : m
          )));
        } else if (evt.event === "error") {
          throw new Error(evt.error || "stream-error");
        }
      }
    } catch (e) {
      console.error("/chat stream error", e);
      const errText =
        "Hubo un problema al conectar con el backend. Revisá que el API esté en http://localhost:8000 y probá de nuevo.";
      setMessages((prev) => prev.map((m) => (
        m.id === asstId ? { ...m, text: errText, sources: [], pending: false } : m
      )));
    }
  };

  return (
    <div className="flex min-h-screen min-w-screen flex-col bg-gray-50">
      <header className="border-b bg-white">
        <div className="mx-auto flex max-w-4xl items-center justify-between px-4 py-3">
          <div className="flex items-center gap-3">
            <span className="text-xs text-gray-500">MVP local</span>
            <label className="text-xs text-gray-600">Bot:</label>
            <select
              className="rounded-md border px-2 py-1 text-sm"
              value={botId}
              onChange={(e) => setBotId(e.target.value)}
            >
              <option value="public-admisiones">public-admisiones</option>
              <option value="interno-academico">interno-academico</option>
            </select>
            {botId === "interno-academico" && (
              <span className="text-[11px] text-gray-500">
                (interno: enviando X-Org-Units: aranceles-becas,general)
              </span>
            )}
          </div>
          <div className="text-[11px] text-gray-500">
            sesión: <code className="font-mono">{sessionId}</code>
          </div>
        </div>
      </header>

      <main className="flex-1 overflow-auto">
        <ChatList messages={messages} />
      </main>

      <footer className="sticky bottom-0 z-10 bg-gradient-to-t from-gray-50 to-transparent px-3 py-3">
        <div className="mx-auto max-w-4xl">
          <ChatInput onSend={handleSend} />
        </div>
      </footer>
    </div>
  );
}
