import React, { useState } from "react"
import Textarea from "../ui/Textarea"
import Button from "../ui/Button"

const ChatInput = ({ onSend }) => {
  const [value, setValue] = useState("")
  const [isLoading, setIsLoading] = useState(false)

  const handleSend = async () => {
    if (!value.trim()) return
    setIsLoading(true)
    try {
      await onSend?.(value)
      setValue("")               
    } finally {
      setIsLoading(false)
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div
      className="
        mx-auto w-full max-w-3xl
        flex items-end gap-2
        rounded-2xl border border-gray-300 bg-white/15 p-2 shadow-sm
        focus-within:ring-1 focus-within:ring-indigo-500 
      "
    >
      <div className="flex-1">
        <Textarea
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Escribe tu mensaje…"
          rows={1}
        />
      </div>

      <div className="flex-shrink-0">
        <Button
          onClick={handleSend}
          loading={isLoading}
          disabled={!value.trim()}
          aria-label="Enviar mensaje"
          size="md"
        >
          Enviar
        </Button>
      </div>
    </div>
  )
}

export default ChatInput
