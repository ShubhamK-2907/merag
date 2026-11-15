import clsx from 'clsx'
import { BookOpen, Brain, ChevronDown, ExternalLink, FileText, Globe, Workflow } from 'lucide-react'
import { useState } from 'react'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { Message, Route, Source } from '../lib/types'

const ROUTE_META: Record<Route, { label: string; icon: typeof BookOpen; className: string }> = {
  index: { label: 'Your documents', icon: BookOpen, className: 'bg-accent/10 text-accent' },
  search: { label: 'Web search', icon: Globe, className: 'bg-amber-500/12 text-amber-700 dark:text-amber-400' },
  general: { label: 'General knowledge', icon: Brain, className: 'bg-subtle text-muted' },
}

export function RouteBadge({ route }: { route: Route }) {
  const m = ROUTE_META[route]
  return (
    <span className={clsx('inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium', m.className)}>
      <m.icon className="size-3.5" aria-hidden />
      {m.label}
    </span>
  )
}

export function Prose({ children }: { children: string }) {
  return (
    <div className="prose prose-stone max-w-none text-[15px] leading-7 dark:prose-invert prose-p:my-3 prose-pre:rounded-xl prose-pre:bg-ink prose-code:before:content-none prose-code:after:content-none prose-a:text-accent">
      <Markdown remarkPlugins={[remarkGfm]}>{children}</Markdown>
    </div>
  )
}

export default function MessageItem({ message }: { message: Message }) {
  if (message.role === 'user') {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-subtle px-4 py-2.5 text-[15px] leading-6 text-ink">
          {message.content}
        </div>
      </div>
    )
  }
  return (
    <div className="space-y-3">
      {message.route && <RouteBadge route={message.route} />}
      <Prose>{message.content}</Prose>
      <Details sources={message.sources} trace={message.trace} />
    </div>
  )
}

function Details({ sources, trace }: { sources: Source[]; trace: string[] }) {
  const [open, setOpen] = useState(false)
  if (!sources.length && !trace.length) return null
  return (
    <div className="rounded-xl border border-line">
      <button
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 px-3 py-2 text-xs font-medium text-muted transition-colors hover:text-ink"
      >
        <Workflow className="size-3.5" aria-hidden />
        How this was answered
        {sources.length > 0 && <span className="text-faint">· {sources.length} sources</span>}
        <ChevronDown className={clsx('ml-auto size-3.5 transition-transform', open && 'rotate-180')} aria-hidden />
      </button>
      {open && (
        <div className="space-y-4 border-t border-line px-3 py-3">
          {trace.length > 0 && (
            <ol className="space-y-1.5">
              {trace.map((t, i) => (
                <li key={i} className="flex gap-2.5 text-xs text-muted">
                  <span className="mt-0.5 flex size-4 shrink-0 items-center justify-center rounded-full bg-subtle font-mono text-[10px] text-faint">
                    {i + 1}
                  </span>
                  <span>{t}</span>
                </li>
              ))}
            </ol>
          )}
          {sources.length > 0 && (
            <ul className="grid gap-2 sm:grid-cols-2">
              {sources.map((s, i) => (
                <li key={i} className="rounded-lg bg-subtle/60 p-2.5">
                  <div className="mb-1 flex items-center gap-1.5 text-xs font-medium text-ink">
                    <span className="font-mono text-faint">[{i + 1}]</span>
                    {s.kind === 'web' ? <Globe className="size-3" aria-hidden /> : <FileText className="size-3" aria-hidden />}
                    {s.url ? (
                      <a href={s.url} target="_blank" rel="noreferrer noopener" className="inline-flex min-w-0 items-center gap-1 hover:underline">
                        <span className="truncate">{s.title}</span>
                        <ExternalLink className="size-3 shrink-0" aria-hidden />
                      </a>
                    ) : (
                      <span className="truncate">{s.title}</span>
                    )}
                    {s.score != null && <span className="ml-auto font-mono text-[10px] text-faint">{s.score.toFixed(2)}</span>}
                  </div>
                  <p className="line-clamp-3 text-xs leading-5 text-muted">{s.snippet}</p>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}
