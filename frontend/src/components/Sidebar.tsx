import clsx from 'clsx'
import { Check, Library, LogOut, MessageSquare, Pencil, Plus, Trash2, X } from 'lucide-react'
import { useState } from 'react'
import { NavLink } from 'react-router-dom'
import type { Conversation, User } from '../lib/types'
import { Button, IconButton, Logo } from './ui'

interface Props {
  user: User
  conversations: Conversation[]
  documentCount: number
  onNew: () => void
  onRename: (id: string, title: string) => void
  onDelete: (id: string) => void
  onOpenKnowledge: () => void
  onLogout: () => void
  onNavigate: () => void
}

export default function Sidebar(p: Props) {
  return (
    <div className="flex h-full flex-col">
      <div className="flex h-14 items-center px-4">
        <Logo />
      </div>

      <div className="px-3 pb-3">
        <Button variant="secondary" className="w-full justify-start" onClick={p.onNew}>
          <Plus className="size-4" aria-hidden /> New chat
        </Button>
      </div>

      <nav className="flex-1 overflow-y-auto px-3" aria-label="Conversations">
        <p className="px-2 pb-1.5 pt-2 text-xs font-medium uppercase tracking-wider text-faint">Chats</p>
        {p.conversations.length === 0 ? (
          <p className="px-2 py-3 text-sm text-faint">No conversations yet.</p>
        ) : (
          <ul className="space-y-0.5">
            {p.conversations.map((c) => (
              <ConversationRow key={c.id} c={c} onRename={p.onRename} onDelete={p.onDelete} onNavigate={p.onNavigate} />
            ))}
          </ul>
        )}
      </nav>

      <div className="space-y-1 border-t border-line p-3">
        <button
          onClick={p.onOpenKnowledge}
          className="flex w-full items-center gap-3 rounded-lg px-2 py-2 text-sm text-ink transition-colors hover:bg-subtle"
        >
          <Library className="size-4 text-muted" aria-hidden />
          <span className="flex-1 text-left">Knowledge base</span>
          <span className="rounded-full bg-subtle px-2 py-0.5 text-xs tabular-nums text-muted">{p.documentCount}</span>
        </button>
        <div className="flex items-center gap-3 rounded-lg px-2 py-2">
          <span className="flex size-8 items-center justify-center rounded-full bg-accent/12 text-sm font-semibold text-accent">
            {p.user.name.charAt(0).toUpperCase()}
          </span>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium text-ink">{p.user.name}</p>
            <p className="truncate text-xs text-muted">{p.user.email}</p>
          </div>
          <IconButton label="Sign out" onClick={p.onLogout}>
            <LogOut className="size-4" />
          </IconButton>
        </div>
      </div>
    </div>
  )
}

function ConversationRow({
  c,
  onRename,
  onDelete,
  onNavigate,
}: {
  c: Conversation
  onRename: Props['onRename']
  onDelete: Props['onDelete']
  onNavigate: () => void
}) {
  const [editing, setEditing] = useState(false)
  const [title, setTitle] = useState(c.title)

  if (editing) {
    const save = () => {
      const t = title.trim()
      if (t && t !== c.title) onRename(c.id, t)
      setEditing(false)
    }
    return (
      <li className="flex items-center gap-1 rounded-lg bg-subtle px-2 py-1">
        <input
          autoFocus
          value={title}
          maxLength={120}
          onChange={(e) => setTitle(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') save()
            if (e.key === 'Escape') setEditing(false)
          }}
          className="min-w-0 flex-1 bg-transparent text-sm text-ink outline-none"
          aria-label="Conversation title"
        />
        <IconButton label="Save title" onClick={save} className="size-7">
          <Check className="size-3.5" />
        </IconButton>
        <IconButton label="Cancel" onClick={() => setEditing(false)} className="size-7">
          <X className="size-3.5" />
        </IconButton>
      </li>
    )
  }

  return (
    <li className="group relative">
      <NavLink
        to={`/c/${c.id}`}
        onClick={onNavigate}
        className={({ isActive }) =>
          clsx(
            'flex items-center gap-2.5 rounded-lg py-2 pl-2 pr-16 text-sm transition-colors',
            isActive ? 'bg-subtle font-medium text-ink' : 'text-muted hover:bg-subtle/70 hover:text-ink',
          )
        }
      >
        <MessageSquare className="size-4 shrink-0 opacity-60" aria-hidden />
        <span className="truncate">{c.title}</span>
      </NavLink>
      <div className="absolute right-1 top-1/2 flex -translate-y-1/2 opacity-0 transition-opacity group-focus-within:opacity-100 group-hover:opacity-100">
        <IconButton label="Rename" className="size-7" onClick={() => { setTitle(c.title); setEditing(true) }}>
          <Pencil className="size-3.5" />
        </IconButton>
        <IconButton
          label="Delete"
          className="size-7 hover:text-danger"
          onClick={() => {
            if (confirm(`Delete “${c.title}”? This cannot be undone.`)) onDelete(c.id)
          }}
        >
          <Trash2 className="size-3.5" />
        </IconButton>
      </div>
    </li>
  )
}
