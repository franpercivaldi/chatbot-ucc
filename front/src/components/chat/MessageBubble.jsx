import Spinner from "../ui/Spinner";

export default function MessageBubble({
  role = "assistant",              // "user" | "assistant"
  text = "",
  sources = [],                    // [{ titulo, tipo, fuente_archivo, fuente_hoja, fuente_fila, periodo }]
  pending = false,
}) {
  const isUser = role === "user";

  return (
    <div className={`w-full flex ${isUser ? "justify-end" : "justify-start"} my-2`}>
      {/* Avatar (assistant) */}
      {!isUser && (
        <div className="mr-2 mt-1 flex h-8 w-8 items-center justify-center select-none rounded-full bg-indigo-600 text-xs font-semibold text-white">
          UCC
        </div>
      )}

      {/* Bubble */}
      <div
        className={[
          "max-w-[82%] rounded-2xl px-4 py-3 shadow-sm",
          isUser
            ? "bg-indigo-600 text-white rounded-br-md"
            : "bg-white text-gray-900 border border-gray-200 rounded-bl-md",
        ].join(" ")}
      >
        {pending ? (
          <div className="flex items-center gap-2 text-sm">
            <Spinner className="h-4 w-4" />
            <span className={isUser ? "text-white/90" : "text-gray-600"}>pensando…</span>
          </div>
        ) : (
          <p className={`whitespace-pre-wrap ${isUser ? "" : "text-gray-800"}`}>{text}</p>
        )}

        {/* Fuentes (sencillo y opcional) */}
        {!isUser && !pending && sources?.length > 0 && (
          <div className="mt-3 grid gap-2 sm:grid-cols-2">
            {sources.map((s, i) => (
              <div key={i} className="rounded-xl border border-gray-200 bg-gray-50 p-2 text-xs text-gray-700">
                <div className="mb-1 font-medium text-gray-900">[{i + 1}] {s?.titulo || s?.tipo || "Fuente"}</div>
                <div className="text-gray-600">
                  {s?.fuente_archivo}
                  {s?.fuente_hoja ? ` · ${s.fuente_hoja}` : ""}
                  {s?.fuente_fila !== undefined ? ` · fila ${s.fuente_fila}` : ""}
                </div>
                {s?.periodo && <div className="text-gray-600">Período: {s.periodo}</div>}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Avatar (user) */}
      {isUser && (
        <div className="ml-2 mt-1 flex h-8 w-8 items-center justify-center select-none rounded-full bg-gray-200 text-xs font-semibold text-gray-700">
          Tú
        </div>
      )}
    </div>
  );
}
