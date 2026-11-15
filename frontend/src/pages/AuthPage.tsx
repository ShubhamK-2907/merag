import { FileSearch, Globe, ShieldCheck, Sparkles } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Link, Navigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { Alert, Button, Field, Logo } from '../components/ui'
import { ApiError } from '../lib/api'

const FEATURES = [
  { icon: FileSearch, title: 'Grounded in your documents', body: 'Upload PDFs or notes. Answers cite the exact passages they came from.' },
  { icon: Sparkles, title: 'Adaptive routing', body: 'Each question takes the cheapest path: your docs, general knowledge, or the web.' },
  { icon: ShieldCheck, title: 'Self-checking', body: 'Retrieved chunks are graded and every answer is verified against its sources.' },
  { icon: Globe, title: 'Private by design', body: 'Your knowledge base is isolated per account, retrieval never crosses users.' },
]

export default function AuthPage({ mode }: { mode: 'login' | 'register' }) {
  const { user, login, register } = useAuth()
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const isLogin = mode === 'login'

  if (user) return <Navigate to="/" replace />

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      if (isLogin) await login(email, password)
      else await register(name, email, password)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="grid min-h-dvh lg:grid-cols-[1.05fr_1fr]">
      <aside className="relative hidden overflow-hidden border-r border-line bg-subtle lg:flex lg:flex-col lg:justify-between lg:p-12">
        <Logo className="text-lg" />
        <div className="max-w-md space-y-10">
          <div className="space-y-4">
            <h1 className="text-4xl font-semibold leading-tight tracking-tight text-ink text-balance">
              Ask questions. Get answers you can trust.
            </h1>
            <p className="text-base text-muted text-pretty">
              MeRAG is an adaptive retrieval-augmented assistant that knows when to read your documents, when to search the
              web, and when to just answer.
            </p>
          </div>
          <ul className="space-y-5">
            {FEATURES.map(({ icon: Icon, title, body }) => (
              <li key={title} className="flex gap-4">
                <span className="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-lg border border-line bg-surface">
                  <Icon className="size-4 text-accent" aria-hidden />
                </span>
                <div>
                  <p className="text-sm font-medium text-ink">{title}</p>
                  <p className="text-sm text-muted">{body}</p>
                </div>
              </li>
            ))}
          </ul>
        </div>
        <p className="text-xs text-faint">FastAPI · LangGraph · MongoDB Atlas Vector Search · React</p>
      </aside>

      <main className="flex items-center justify-center px-4 py-12 sm:px-8">
        <div className="w-full max-w-sm space-y-8">
          <div className="space-y-2">
            <Logo className="mb-8 text-lg lg:hidden" />
            <h2 className="text-2xl font-semibold tracking-tight text-ink">
              {isLogin ? 'Welcome back' : 'Create your account'}
            </h2>
            <p className="text-sm text-muted">
              {isLogin ? 'Sign in to continue to your workspace.' : 'Start building your private knowledge base.'}
            </p>
          </div>

          <form onSubmit={onSubmit} className="space-y-4" noValidate={false}>
            {error && <Alert>{error}</Alert>}
            {!isLogin && (
              <Field label="Name" autoComplete="name" required maxLength={80} value={name} onChange={(e) => setName(e.target.value)} />
            )}
            <Field
              label="Email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
            <Field
              label="Password"
              type="password"
              autoComplete={isLogin ? 'current-password' : 'new-password'}
              required
              minLength={isLogin ? 1 : 8}
              maxLength={72}
              hint={isLogin ? undefined : 'At least 8 characters.'}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            <Button type="submit" className="w-full" loading={submitting}>
              {isLogin ? 'Sign in' : 'Create account'}
            </Button>
          </form>

          <p className="text-center text-sm text-muted">
            {isLogin ? "Don't have an account? " : 'Already have an account? '}
            <Link to={isLogin ? '/register' : '/login'} className="font-medium text-ink underline-offset-4 hover:underline">
              {isLogin ? 'Sign up' : 'Sign in'}
            </Link>
          </p>
        </div>
      </main>
    </div>
  )
}
