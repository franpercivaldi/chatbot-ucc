// src/Chat.jsx
import { useState } from "react";
import ChatList from "./components/chat/ChatList";
import ChatInput from "./components/chat/ChatInput";
import { chat as chatApi } from "./lib/api";

export default function Chat() {
  const [messages, setMessages] = useState([]);
  const [pending, setPending] = useState(false);

  const genId = () =>
    (globalThis.crypto?.randomUUID?.() ?? String(Date.now() + Math.random()));

  const handleSend = async (text) => {
    const userMsg = { id: genId(), role: "user", text };
    setMessages((prev) => [...prev, userMsg]);
    setPending(true);

    try {
      // Si querés pasar filtros: { periodo: "2025", facultad: "Ciencias sociales" }
      const data = await chatApi(text /* , { periodo, facultad, carrera, modalidad } */);

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
      // opcional: console.error(e)
    } finally {
      setPending(false);
    }
  };

  return (
    <div className="flex min-h-screen min-w-screen flex-col bg-gray-50">
      <header className="border-b bg-white">
        <div className="mx-auto flex max-w-4xl items-center justify-between px-4 py-3">
          <span className="text-xs text-gray-500">MVP local</span>
        </div>
      </header>

      <main className="flex-1 overflow-auto">
        <ChatList messages={messages} pending={pending} />
      </main>

      <footer className="sticky bottom-0 z-10 bg-gradient-to-t from-gray-50 to-transparent px-3 py-3">
        <ChatInput onSend={handleSend} />
      </footer>
    </div>
  );
}
