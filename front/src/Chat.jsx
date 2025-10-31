import { useMemo, useState } from "react";
import ChatList from "./components/chat/ChatList";
import ChatInput from "./components/chat/ChatInput";
import { chat as chatApi } from "./lib/api";

export default function Chat() {
  const [messages, setMessages] = useState([]);
  const [pending, setPending] = useState(false);
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
    setMessages((prev) => [...prev, userMsg]);
    setPending(true);

      try {
      const meta = null;

      // Pedimos debug para ver retrieval_debug y poder investigar por qué no hay hits
      const data = await chatApi(text, meta, {
        botId,
        sessionId,
        debug: true,
      });

  // Logueamos la respuesta completa en la consola para diagnóstico rápido
  // (el usuario pidió una solución simple sin auth)
  console.log("/chat response:", data);

      const asstMsg = {
        id: genId(),
        role: "assistant",
        text: data?.answer || "No pude generar una respuesta.",
        sources: Array.isArray(data?.sources) ? data.sources : [],
      };
      setMessages((prev) => [...prev, asstMsg]);
    } catch (e) {
      const errMsg = {
        id: genId(),
        role: "assistant",
        text:
          "Hubo un problema al conectar con el backend. Revisá que el API esté en http://localhost:8000 y probá de nuevo.",
        sources: [],
      };
      setMessages((prev) => [...prev, errMsg]);
    } finally {
      setPending(false);
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
        <ChatList messages={messages} pending={pending} />
      </main>

      <footer className="sticky bottom-0 z-10 bg-gradient-to-t from-gray-50 to-transparent px-3 py-3">
        <div className="mx-auto max-w-4xl">
          <ChatInput onSend={handleSend} />
        </div>
      </footer>
    </div>
  );
}
