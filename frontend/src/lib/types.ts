export type Route = 'index' | 'general' | 'search'

export interface User {
  id: string
  name: string
  email: string
  created_at: string
}

export interface TokenResponse {
  access_token: string
  token_type: 'bearer'
  expires_in: number
  user: User
}

export interface Conversation {
  id: string
  title: string
  created_at: string
  updated_at: string
}

export interface Source {
  kind: 'document' | 'web'
  title: string
  snippet: string
  document_id?: string | null
  url?: string | null
  score?: number | null
}

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  route?: Route | null
  sources: Source[]
  trace: string[]
  created_at: string
}

export interface DocumentItem {
  id: string
  filename: string
  description: string
  size_bytes: number
  chunk_count: number
  created_at: string
}

export type StreamEvent =
  | { event: 'step'; data: { node: string; trace: string[] } }
  | { event: 'token'; data: { text: string } }
  | { event: 'reset'; data: Record<string, never> }
  | { event: 'done'; data: { message: Message } }
  | { event: 'error'; data: { detail: string } }
