import type { Conversation, DocumentItem, Message, StreamEvent, TokenResponse, User } from './types'

// Dev: separate API server. Prod: same origin (the API container serves this app) unless overridden.
export const API_URL = (import.meta.env.VITE_API_URL ?? (import.meta.env.DEV ? 'http://localhost:8000' : '')).replace(/\/$/, '')
const TOKEN_KEY = 'merag.token'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

export const tokenStore = {
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (t: string) => localStorage.setItem(TOKEN_KEY, t),
  clear: () => localStorage.removeItem(TOKEN_KEY),
}

let onUnauthorized: () => void = () => {}
export const setUnauthorizedHandler = (fn: () => void) => {
  onUnauthorized = fn
}

async function errorMessage(res: Response): Promise<string> {
  try {
    const body = await res.json()
    if (typeof body.detail === 'string') return body.detail
    if (Array.isArray(body.detail))
      return body.detail
        .map((d: { msg: string }) => d.msg.replace(/^Value error, /, '').replace(/^value is not a valid email address: /, ''))
        .join(' ')
    if (typeof body.error === 'string') return body.error
  } catch {
    /* non-JSON error body */
  }
  return res.status === 429 ? 'Too many requests. Please wait a moment.' : `Request failed (${res.status})`
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  const token = tokenStore.get()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  if (init.body && !(init.body instanceof FormData)) headers.set('Content-Type', 'application/json')

  let res: Response
  try {
    res = await fetch(`${API_URL}${path}`, { ...init, headers })
  } catch {
    throw new ApiError(0, 'Cannot reach the server. It may be waking up, try again in a few seconds.')
  }
  if (res.status === 401 && token) onUnauthorized()
  if (!res.ok) throw new ApiError(res.status, await errorMessage(res))
  return (res.status === 204 ? undefined : await res.json()) as T
}

export const api = {
  register: (name: string, email: string, password: string) =>
    request<TokenResponse>('/api/auth/register', { method: 'POST', body: JSON.stringify({ name, email, password }) }),
  login: (email: string, password: string) =>
    request<TokenResponse>('/api/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) }),
  me: () => request<User>('/api/auth/me'),

  listConversations: () => request<Conversation[]>('/api/conversations'),
  createConversation: () => request<Conversation>('/api/conversations', { method: 'POST', body: '{}' }),
  renameConversation: (id: string, title: string) =>
    request<Conversation>(`/api/conversations/${id}`, { method: 'PATCH', body: JSON.stringify({ title }) }),
  deleteConversation: (id: string) => request<void>(`/api/conversations/${id}`, { method: 'DELETE' }),
  listMessages: (id: string) => request<Message[]>(`/api/conversations/${id}/messages`),

  listDocuments: () => request<DocumentItem[]>('/api/documents'),
  uploadDocument: (file: File, description: string) => {
    const form = new FormData()
    form.append('file', file)
    if (description.trim()) form.append('description', description.trim())
    return request<DocumentItem>('/api/documents', { method: 'POST', body: form })
  },
  deleteDocument: (id: string) => request<void>(`/api/documents/${id}`, { method: 'DELETE' }),
}

/**
 * POST a message and consume the Server-Sent Events stream.
 * EventSource can't send POST bodies or auth headers, so we parse SSE over fetch.
 */
export async function streamMessage(
  conversationId: string,
  content: string,
  onEvent: (e: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`${API_URL}/api/conversations/${conversationId}/messages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${tokenStore.get() ?? ''}` },
    body: JSON.stringify({ content }),
    signal,
  })
  if (res.status === 401) onUnauthorized()
  if (!res.ok || !res.body) throw new ApiError(res.status, await errorMessage(res))

  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader()
  let buffer = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += value.replace(/\r\n/g, '\n')
    let sep: number
    while ((sep = buffer.indexOf('\n\n')) !== -1) {
      const raw = buffer.slice(0, sep)
      buffer = buffer.slice(sep + 2)
      let event = 'message'
      const data: string[] = []
      for (const line of raw.split('\n')) {
        if (line.startsWith('event:')) event = line.slice(6).trim()
        else if (line.startsWith('data:')) data.push(line.slice(5).trimStart())
      }
      if (!data.length || event === 'ping') continue
      onEvent({ event, data: JSON.parse(data.join('\n')) } as StreamEvent)
    }
  }
}
