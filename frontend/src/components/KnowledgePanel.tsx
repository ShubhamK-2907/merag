import clsx from 'clsx'
import { FileText, Trash2, UploadCloud, X } from 'lucide-react'
import { useRef, useState, type DragEvent } from 'react'
import { api, ApiError } from '../lib/api'
import type { DocumentItem } from '../lib/types'
import { Alert, Button, formatBytes, IconButton } from './ui'

const ACCEPT = '.pdf,.txt,.md'

export default function KnowledgePanel({
  documents,
  onChange,
  onClose,
}: {
  documents: DocumentItem[]
  onChange: () => void
  onClose: () => void
}) {
  const [file, setFile] = useState<File | null>(null)
  const [description, setDescription] = useState('')
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [dragging, setDragging] = useState(false)
  const input = useRef<HTMLInputElement>(null)

  const pick = (f: File | undefined) => {
    setError(null)
    if (!f) return
    if (!/\.(pdf|txt|md)$/i.test(f.name)) return setError('Only PDF, TXT and MD files are supported.')
    if (f.size > 10 * 1024 * 1024) return setError('File is larger than 10 MB.')
    setFile(f)
  }

  const upload = async () => {
    if (!file) return
    setUploading(true)
    setError(null)
    try {
      await api.uploadDocument(file, description)
      setFile(null)
      setDescription('')
      onChange()
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Upload failed.')
    } finally {
      setUploading(false)
    }
  }

  const remove = async (d: DocumentItem) => {
    if (!confirm(`Remove “${d.filename}” from your knowledge base?`)) return
    try {
      await api.deleteDocument(d.id)
      onChange()
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Delete failed.')
    }
  }

  const onDrop = (e: DragEvent) => {
    e.preventDefault()
    setDragging(false)
    pick(e.dataTransfer.files[0])
  }

  return (
    <div className="flex h-full flex-col">
      <header className="flex h-14 items-center justify-between border-b border-line px-5">
        <div>
          <h2 className="text-sm font-semibold text-ink">Knowledge base</h2>
        </div>
        <IconButton label="Close" onClick={onClose}>
          <X className="size-4" />
        </IconButton>
      </header>

      <div className="flex-1 space-y-6 overflow-y-auto p-5">
        <p className="text-sm text-muted">
          Documents are split into chunks, embedded, and searched only for your account. The router uses each description to
          decide when to look here.
        </p>

        <section className="space-y-3">
          <div
            role="button"
            tabIndex={0}
            onClick={() => input.current?.click()}
            onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && input.current?.click()}
            onDragOver={(e) => {
              e.preventDefault()
              setDragging(true)
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            className={clsx(
              'flex cursor-pointer flex-col items-center gap-2 rounded-xl border-2 border-dashed px-4 py-8 text-center transition-colors',
              dragging ? 'border-accent bg-accent/5' : 'border-line hover:border-ink/25',
            )}
          >
            <UploadCloud className="size-6 text-muted" aria-hidden />
            {file ? (
              <p className="text-sm font-medium text-ink">
                {file.name} <span className="font-normal text-muted">· {formatBytes(file.size)}</span>
              </p>
            ) : (
              <>
                <p className="text-sm font-medium text-ink">Drop a file or click to browse</p>
                <p className="text-xs text-muted">PDF, TXT or MD · up to 10 MB</p>
              </>
            )}
            <input ref={input} type="file" accept={ACCEPT} hidden onChange={(e) => pick(e.target.files?.[0])} />
          </div>

          {file && (
            <>
              <label className="block space-y-1.5">
                <span className="text-sm font-medium text-ink">
                  Description <span className="font-normal text-faint">(optional)</span>
                </span>
                <textarea
                  rows={2}
                  maxLength={300}
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="e.g. My resume: education, projects and work history"
                  className="w-full resize-none rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink placeholder:text-faint focus:border-accent focus:outline-none focus:ring-3 focus:ring-accent/15"
                />
                <span className="text-xs text-muted">Leave empty and one will be generated automatically.</span>
              </label>
              <div className="flex gap-2">
                <Button className="flex-1" loading={uploading} onClick={upload}>
                  {uploading ? 'Processing…' : 'Add to knowledge base'}
                </Button>
                <Button variant="secondary" onClick={() => setFile(null)} disabled={uploading}>
                  Cancel
                </Button>
              </div>
            </>
          )}
          {error && <Alert>{error}</Alert>}
        </section>

        <section className="space-y-2">
          <h3 className="text-xs font-medium uppercase tracking-wider text-faint">Documents · {documents.length}</h3>
          {documents.length === 0 ? (
            <p className="py-4 text-sm text-faint">Nothing here yet.</p>
          ) : (
            <ul className="divide-y divide-line rounded-xl border border-line">
              {documents.map((d) => (
                <li key={d.id} className="group flex gap-3 p-3">
                  <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-subtle">
                    <FileText className="size-4 text-muted" aria-hidden />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-ink">{d.filename}</p>
                    <p className="line-clamp-2 text-xs text-muted">{d.description}</p>
                    <p className="mt-1 text-xs text-faint">
                      {d.chunk_count} chunks · {formatBytes(d.size_bytes)}
                    </p>
                  </div>
                  <IconButton label={`Remove ${d.filename}`} className="hover:text-danger" onClick={() => remove(d)}>
                    <Trash2 className="size-4" />
                  </IconButton>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  )
}
