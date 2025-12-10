import Spinner from "../ui/Spinner";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

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
          <div
            className={`prose prose-sm max-w-none whitespace-pre-wrap break-words ${
              isUser ? "prose-invert text-white" : "text-gray-900"
            }`}
          >
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                strong: ({node, ...props}) => <strong {...props} className="font-semibold" />,
                em: ({node, ...props}) => <em {...props} className="italic" />,
                a: ({node, ...props}) => <a {...props} className="text-indigo-600 underline" />,
                ul: ({node, ...props}) => <ul {...props} className="list-disc pl-5" />,
                ol: ({node, ...props}) => <ol {...props} className="list-decimal pl-5" />,
                li: ({node, ...props}) => <li {...props} className="my-0.5" />,
              }}
            >
              {text}
            </ReactMarkdown>
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
