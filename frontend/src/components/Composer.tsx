import { ArrowUp, Square } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

export default function Composer({
  busy,
  onSend,
  onStop,
}: {
  busy: boolean
  onSend: (text: string) => void
  onStop: () => void
}) {
  const [text, setText] = useState('')
  const ref = useRef<HTMLTextAreaElement>(null)

  // Auto-grow up to ~8 lines.
  useEffect(() => {
    const el = ref.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`
  }, [text])

  const submit = () => {
    const t = text.trim()
    if (!t || busy) return
    onSend(t)
    setText('')
  }

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        submit()
      }}
      className="flex items-end gap-2 rounded-2xl border border-line bg-surface p-2 shadow-sm transition-shadow focus-within:border-accent/50 focus-within:ring-4 focus-within:ring-accent/10"
    >
      <textarea
        ref={ref}
        rows={1}
        value={text}
        maxLength={4000}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault()
            submit()
          }
        }}
        placeholder="Ask anything about your documents…"
        aria-label="Message"
        className="max-h-[200px] min-h-10 flex-1 resize-none bg-transparent px-2 py-2 text-[15px] leading-6 text-ink placeholder:text-faint focus:outline-none"
      />
      {busy ? (
        <button
          type="button"
          onClick={onStop}
          aria-label="Stop generating"
          className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-ink text-canvas transition-colors hover:bg-ink/85"
        >
          <Square className="size-3.5 fill-current" />
        </button>
      ) : (
        <button
          type="submit"
          disabled={!text.trim()}
          aria-label="Send message"
          className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-ink text-canvas transition-colors hover:bg-ink/85 disabled:bg-line disabled:text-faint"
        >
          <ArrowUp className="size-4.5" />
        </button>
      )}
    </form>
  )
}
