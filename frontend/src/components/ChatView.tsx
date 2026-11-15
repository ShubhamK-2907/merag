import { Check, FileUp, Loader2 } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { api, ApiError, streamMessage } from '../lib/api'
import type { Message } from '../lib/types'
import Composer from './Composer'
import MessageItem, { Prose } from './MessageItem'
import { Alert, Spinner } from './ui'

const NODE_LABEL: Record<string, string> = {
  contextualize: 'Understanding the question',
  route: 'Choosing a strategy',
  retrieve: 'Searching your documents',
  grade: 'Checking relevance',
  rewrite: 'Refining the query',
  web_search: 'Searching the web',
  generate: 'Writing the answer',
  verify: 'Verifying against sources',
  general: 'Answering',
}

interface Pending {
  question: string
  steps: string[]
  text: string
}

interface Props {
  conversationId?: string
  documentCount: number
  ensureConversation: () => Promise<string>
  onActivity: () => void
  onOpenKnowledge: () => void
}

export default function ChatView({ conversationId, documentCount, ensureConversation, onActivity, onOpenKnowledge }: Props) {
  const [messages, setMessages] = useState<Message[]>([])
  const [loading, setLoading] = useState(false)
  const [pending, setPending] = useState<Pending | null>(null)
  const [error, setError] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const justCreated = useRef<string | null>(null)
  const scroller = useRef<HTMLDivElement>(null)
  const stick = useRef(true)

  // Load history when switching conversations (but not for one we just created mid-send).
  useEffect(() => {
    setError(null)
    if (!conversationId) {
      setMessages([])
      return
    }
    if (justCreated.current === conversationId) {
      justCreated.current = null
      return
    }
    let cancelled = false
    setLoading(true)
    api
      .listMessages(conversationId)
      .then((m) => !cancelled && setMessages(m))
      .catch((e) => !cancelled && setError(e instanceof ApiError ? e.message : 'Could not load messages'))
      .finally(() => !cancelled && setLoading(false))
    return () => {
      cancelled = true
    }
  }, [conversationId])

  useEffect(() => {
    const el = scroller.current
    if (el && stick.current) el.scrollTop = el.scrollHeight
  }, [messages, pending])

  const send = async (text: string) => {
    setError(null)
    stick.current = true
    const optimistic: Message = {
      id: `local-${Date.now()}`,
      role: 'user',
      content: text,
      sources: [],
      trace: [],
      created_at: new Date().toISOString(),
    }
    setPending({ question: text, steps: [], text: '' })
    const controller = new AbortController()
    abortRef.current = controller
    try {
      let id = conversationId
      if (!id) {
        id = await ensureConversation()
        justCreated.current = id
      }
      setMessages((m) => [...m, optimistic])
      await streamMessage(
        id,
        text,
        (e) => {
          switch (e.event) {
            case 'step':
              setPending((p) => p && { ...p, steps: [...p.steps, e.data.node] })
              break
            case 'token':
              setPending((p) => p && { ...p, text: p.text + e.data.text })
              break
            case 'reset':
              setPending((p) => p && { ...p, text: '' })
              break
            case 'done':
              setMessages((m) => [...m, e.data.message])
              break
            case 'error':
              setError(e.data.detail)
              break
          }
        },
        controller.signal,
      )
    } catch (e) {
      if (!(e instanceof DOMException && e.name === 'AbortError')) {
        setError(e instanceof ApiError ? e.message : 'Connection lost. Please try again.')
      }
    } finally {
      setPending(null)
      abortRef.current = null
      onActivity()
    }
  }

  const empty = !loading && messages.length === 0 && !pending

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div
        ref={scroller}
        onScroll={(e) => {
          const el = e.currentTarget
          stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80
        }}
        className="min-h-0 flex-1 overflow-y-auto"
      >
        <div className="mx-auto w-full max-w-3xl px-4 py-8 sm:px-6">
          {loading && (
            <div className="flex justify-center py-16">
              <Spinner />
            </div>
          )}
          {empty && <EmptyState documentCount={documentCount} onPick={send} onOpenKnowledge={onOpenKnowledge} />}
          <div className="space-y-8">
            {messages.map((m) => (
              <MessageItem key={m.id} message={m} />
            ))}
            {pending && <PendingAnswer pending={pending} />}
          </div>
          {error && (
            <div className="mt-6">
              <Alert>{error}</Alert>
            </div>
          )}
        </div>
      </div>

      <div className="mx-auto w-full max-w-3xl px-4 pb-4 sm:px-6">
        <Composer busy={Boolean(pending)} onSend={send} onStop={() => abortRef.current?.abort()} />
        <p className="mt-2 text-center text-xs text-faint">Answers are checked against sources, but can still be wrong.</p>
      </div>
    </div>
  )
}

function PendingAnswer({ pending }: { pending: Pending }) {
  if (pending.text) return <Prose>{pending.text + ' ▍'}</Prose>
  return (
    <ol className="space-y-2" aria-live="polite">
      {pending.steps.map((node, i) => (
        <li key={i} className="flex items-center gap-2.5 text-sm text-muted">
          <Check className="size-4 text-accent" aria-hidden />
          {NODE_LABEL[node] ?? node}
        </li>
      ))}
      <li className="flex items-center gap-2.5 text-sm text-ink">
        <Loader2 className="size-4 animate-spin text-accent" aria-hidden />
        <span className="animate-pulse">{pending.steps.length ? 'Working…' : 'Starting…'}</span>
      </li>
    </ol>
  )
}

function EmptyState({
  documentCount,
  onPick,
  onOpenKnowledge,
}: {
  documentCount: number
  onPick: (q: string) => void
  onOpenKnowledge: () => void
}) {
  const suggestions =
    documentCount > 0
      ? ['Summarize my documents in 5 bullet points', 'What are the key skills mentioned?', 'What is the latest news in AI this week?']
      : ['Explain retrieval-augmented generation simply', 'What is the latest news in AI this week?', 'How does vector search work?']
  return (
    <div className="flex flex-col items-center py-12 text-center sm:py-20">
      <h1 className="text-2xl font-semibold tracking-tight text-ink sm:text-3xl">What would you like to know?</h1>
      <p className="mt-3 max-w-md text-sm text-muted text-pretty">
        {documentCount > 0
          ? `I can answer from your ${documentCount} document${documentCount > 1 ? 's' : ''}, general knowledge, or the web, and I'll pick the right one.`
          : 'Upload a PDF or notes to get answers grounded in your own documents, or just ask anything.'}
      </p>
      {documentCount === 0 && (
        <button
          onClick={onOpenKnowledge}
          className="mt-6 inline-flex items-center gap-2 rounded-lg border border-dashed border-line px-4 py-2.5 text-sm font-medium text-ink transition-colors hover:border-accent hover:text-accent"
        >
          <FileUp className="size-4" aria-hidden /> Upload your first document
        </button>
      )}
      <div className="mt-10 grid w-full gap-2 sm:grid-cols-3">
        {suggestions.map((s) => (
          <button
            key={s}
            onClick={() => onPick(s)}
            className="rounded-xl border border-line bg-surface px-4 py-3 text-left text-sm text-muted transition-colors hover:border-ink/20 hover:text-ink"
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  )
}
