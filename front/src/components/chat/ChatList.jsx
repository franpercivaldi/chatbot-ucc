import { useEffect, useRef } from "react";
import MessageBubble from "./MessageBubble";

export default function ChatList({ messages = [] }) {
  const endRef = useRef(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  return (
    <div className="mx-auto w-full max-w-3xl px-3 py-4">
      {messages.length === 0 && (
        <div className="mt-16 text-center text-sm text-gray-500">
          Empezá preguntando por carreras, becas, aranceles o fechas.
        </div>
      )}

      {messages.map((m, idx) => (
        <MessageBubble
          key={m.id ?? idx}
          role={m.role}
          text={m.text}
          sources={m.sources}
          pending={m.pending}
        />
      ))}

      <div ref={endRef} />
    </div>
  );
}
