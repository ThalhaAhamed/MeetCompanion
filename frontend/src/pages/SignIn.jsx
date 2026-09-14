import { useState } from 'react'
import Logo from '../components/Logo'
import { Card, ErrorMessage, Field, Spinner } from '../components/ui'
import { addMember, login } from '../api'

export default function SignIn({ onSignedIn, hasMembers = true }) {
  // Fresh install (no account yet): open on Create account, not a sign-in
  // form nobody can use.
  const [mode, setMode] = useState(hasMembers ? 'signin' : 'create')
  const [form, setForm] = useState({
    name: '',
    email: '',
    password: '',
    workspace_name: '',
    join_code: '',
  })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  function update(key, value) {
    setForm((current) => ({ ...current, [key]: value }))
  }

  async function submit(event) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      if (mode === 'signin') {
        await login(form.email.trim(), form.password)
      } else {
        await addMember({
          name: form.name.trim(),
          email: form.email.trim(),
          password: form.password,
          workspace_name: form.workspace_name.trim() || undefined,
          join_code: form.join_code.trim() || undefined,
        })
        await login(form.email.trim(), form.password)
      }
      onSignedIn?.()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div
      className="flex min-h-screen items-center justify-center px-5 py-12"
      style={{ backgroundColor: 'var(--surface-page)' }}
    >
      <div className="w-full max-w-md">
        <div className="mb-8 flex flex-col items-center text-center">
          <Logo variant="icon" size={64} />
          <h1 className="mt-5 text-2xl font-semibold">Meet Companion</h1>
          <p
            className="mt-1.5 text-[0.7rem] font-semibold uppercase tracking-[0.22em]"
            style={{ color: 'var(--text-faint)' }}
          >
            Make meeting data smarter.
          </p>
        </div>

        <Card>
          <div
            className="mb-5 grid grid-cols-2 gap-1 rounded-xl p-1"
            style={{ backgroundColor: 'var(--surface-raised)' }}
          >
            {['signin', 'create'].map((value) => (
              <button
                key={value}
                type="button"
                className="rounded-lg py-1.5 text-sm font-medium transition-colors"
                style={{
                  backgroundColor: mode === value ? 'var(--surface-panel)' : 'transparent',
                  color: mode === value ? 'var(--text-strong)' : 'var(--text-muted)',
                }}
                onClick={() => {
                  setMode(value)
                  setError(null)
                }}
              >
                {value === 'signin' ? 'Sign in' : 'Create account'}
              </button>
            ))}
          </div>

          <form onSubmit={submit}>
            {mode === 'create' && (
              <Field label="Your name" htmlFor="name">
                <input
                  id="name"
                  className="mc-input"
                  value={form.name}
                  onChange={(event) => update('name', event.target.value)}
                  autoComplete="name"
                />
              </Field>
            )}

            <Field label="Email" htmlFor="email">
              <input
                id="email"
                type="email"
                className="mc-input"
                required
                value={form.email}
                onChange={(event) => update('email', event.target.value)}
                autoComplete="email"
              />
            </Field>

            <Field label="Password" htmlFor="password">
              <input
                id="password"
                type="password"
                className="mc-input"
                required
                value={form.password}
                onChange={(event) => update('password', event.target.value)}
                autoComplete={mode === 'signin' ? 'current-password' : 'new-password'}
              />
            </Field>

            {mode === 'create' && (
              <>
                <Field
                  label="Workspace name"
                  hint="Leave blank to join an existing workspace with a code."
                  htmlFor="workspace"
                >
                  <input
                    id="workspace"
                    className="mc-input"
                    value={form.workspace_name}
                    onChange={(event) => update('workspace_name', event.target.value)}
                  />
                </Field>
                <Field label="Join code" hint="Optional — to join a teammate's workspace." htmlFor="join">
                  <input
                    id="join"
                    className="mc-input"
                    value={form.join_code}
                    onChange={(event) => update('join_code', event.target.value)}
                  />
                </Field>
              </>
            )}

            {error && (
              <div className="mb-4">
                <ErrorMessage title={mode === 'signin' ? 'Could not sign you in' : 'Could not create your account'} detail={error} />
              </div>
            )}

            <button type="submit" className="mc-btn mc-btn-primary w-full" disabled={busy}>
              {busy ? <Spinner size={14} /> : null}
              {mode === 'signin' ? 'Sign in' : 'Create account'}
            </button>
          </form>
        </Card>

        <p className="mt-5 text-center text-xs" style={{ color: 'var(--text-faint)' }}>
          Forgot your password? A workspace owner can reset it from the Members page.
        </p>
      </div>
    </div>
  )
}
