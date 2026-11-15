import clsx from 'clsx'
import { Library, Menu } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import ChatView from '../components/ChatView'
import KnowledgePanel from '../components/KnowledgePanel'
import Sidebar from '../components/Sidebar'
import { IconButton } from '../components/ui'
import { api } from '../lib/api'
import type { Conversation, DocumentItem } from '../lib/types'

export default function AppShell() {
  const { user, logout } = useAuth()
  const { id } = useParams()
  const navigate = useNavigate()
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [documents, setDocuments] = useState<DocumentItem[]>([])
  const [navOpen, setNavOpen] = useState(false)
  const [kbOpen, setKbOpen] = useState(false)

  const loadConversations = useCallback(() => api.listConversations().then(setConversations).catch(() => {}), [])
  const loadDocuments = useCallback(() => api.listDocuments().then(setDocuments).catch(() => {}), [])

  useEffect(() => {
    loadConversations()
    loadDocuments()
  }, [loadConversations, loadDocuments])

  // Close overlays with Escape.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setNavOpen(false)
        setKbOpen(false)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const active = conversations.find((c) => c.id === id)

  const ensureConversation = async () => {
    const conv = await api.createConversation()
    setConversations((cs) => [conv, ...cs])
    navigate(`/c/${conv.id}`)
    return conv.id
  }

  const remove = async (cid: string) => {
    await api.deleteConversation(cid)
    setConversations((cs) => cs.filter((c) => c.id !== cid))
    if (cid === id) navigate('/')
  }

  const rename = async (cid: string, title: string) => {
    const updated = await api.renameConversation(cid, title)
    setConversations((cs) => cs.map((c) => (c.id === cid ? updated : c)))
  }

  if (!user) return null

  return (
    <div className="flex h-dvh overflow-hidden bg-canvas">
      {/* Sidebar: static on desktop, slide-over on mobile */}
      <div
        className={clsx('fixed inset-0 z-30 bg-ink/30 backdrop-blur-[1px] transition-opacity lg:hidden', navOpen ? 'opacity-100' : 'pointer-events-none opacity-0')}
        onClick={() => setNavOpen(false)}
        aria-hidden
      />
      <aside
        className={clsx(
          'fixed inset-y-0 left-0 z-40 w-72 border-r border-line bg-canvas transition-transform lg:static lg:translate-x-0',
          navOpen ? 'translate-x-0' : '-translate-x-full',
        )}
      >
        <Sidebar
          user={user}
          conversations={conversations}
          documentCount={documents.length}
          onNew={() => {
            navigate('/')
            setNavOpen(false)
          }}
          onRename={rename}
          onDelete={remove}
          onOpenKnowledge={() => {
            setKbOpen(true)
            setNavOpen(false)
          }}
          onLogout={logout}
          onNavigate={() => setNavOpen(false)}
        />
      </aside>

      <main className="flex min-w-0 flex-1 flex-col bg-surface lg:my-2 lg:mr-2 lg:rounded-2xl lg:border lg:border-line">
        <header className="flex h-14 shrink-0 items-center gap-2 border-b border-line px-3 sm:px-4">
          <IconButton label="Open menu" className="lg:hidden" onClick={() => setNavOpen(true)}>
            <Menu className="size-4.5" />
          </IconButton>
          <h1 className="min-w-0 flex-1 truncate text-sm font-medium text-ink">{active?.title ?? 'New chat'}</h1>
          <button
            onClick={() => setKbOpen(true)}
            className="inline-flex h-8 items-center gap-2 rounded-lg border border-line px-3 text-xs font-medium text-muted transition-colors hover:text-ink"
          >
            <Library className="size-3.5" aria-hidden />
            <span className="hidden sm:inline">Knowledge base</span>
            <span className="tabular-nums">{documents.length}</span>
          </button>
        </header>
        <ChatView
          conversationId={id}
          documentCount={documents.length}
          ensureConversation={ensureConversation}
          onActivity={loadConversations}
          onOpenKnowledge={() => setKbOpen(true)}
        />
      </main>

      {/* Knowledge base drawer */}
      <div
        className={clsx('fixed inset-0 z-30 bg-ink/30 backdrop-blur-[1px] transition-opacity', kbOpen ? 'opacity-100' : 'pointer-events-none opacity-0')}
        onClick={() => setKbOpen(false)}
        aria-hidden
      />
      <aside
        role="dialog"
        aria-label="Knowledge base"
        aria-hidden={!kbOpen}
        className={clsx(
          'fixed inset-y-0 right-0 z-40 w-full max-w-md border-l border-line bg-surface shadow-xl transition-transform',
          kbOpen ? 'translate-x-0' : 'translate-x-full',
        )}
      >
        {kbOpen && <KnowledgePanel documents={documents} onChange={loadDocuments} onClose={() => setKbOpen(false)} />}
      </aside>
    </div>
  )
}
