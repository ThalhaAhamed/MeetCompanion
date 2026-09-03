import { useEffect, useState } from 'react'
import { checkAuth, login, addMember } from './api'

export default function AuthGate({ children }) {
  const [status, setStatus] = useState('checking') // checking | gate | open
  const [mode, setMode] = useState('signin') // signin | signup
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  function recheck() {
    checkAuth()
      .then((d) => setStatus(d.authenticated ? 'open' : 'gate'))
      .catch(() => setStatus('gate'))
  }

  useEffect(recheck, [])
  useEffect(() => {
    const onUnauthorized = () => setStatus((s) => (s === 'open' ? 'gate' : s))
    window.addEventListener('hub:unauthorized', onUnauthorized)
    return () => window.removeEventListener('hub:unauthorized', onUnauthorized)
  }, [])

  function switchMode(next) {
    setMode(next)
    setError(null)
  }

  async function submitLogin(e) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await login(email, password)
      setPassword('')
      setStatus('open')
    } catch (e) {
      setError('Incorrect email or password.')
    } finally {
      setBusy(false)
    }
  }

  async function submitSignup(e) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await addMember({ name, email, password })
      await login(email, password)
      setPassword('')
      setStatus('open')
    } catch (e) {
      setError(e.message.includes('409') ? 'That email is already a member — try signing in.' : 'Could not create the account.')
    } finally {
      setBusy(false)
    }
  }

  if (status === 'checking') {
    return <div className="gate-screen">Loading…</div>
  }

  if (status === 'gate') {
    return (
      <div className="gate-screen">
        <div className="gate-card">
          <div className="gate-title">MeetStream Companion</div>
          <div className="gate-tabs">
            <button type="button" className={mode === 'signin' ? 'active' : ''} onClick={() => switchMode('signin')}>Sign in</button>
            <button type="button" className={mode === 'signup' ? 'active' : ''} onClick={() => switchMode('signup')}>Create account</button>
          </div>

          {mode === 'signin' ? (
            <form onSubmit={submitLogin}>
              <div className="gate-subtitle">Sign in to open the hub.</div>
              <input type="email" autoFocus placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} />
              <input type="password" placeholder="Password" value={password} onChange={(e) => setPassword(e.target.value)} />
              <button type="submit" disabled={busy || !email || !password}>
                {busy ? 'Signing in…' : 'Sign in'}
              </button>
              {error && <div className="gate-error">{error}</div>}
            </form>
          ) : (
            <form onSubmit={submitSignup}>
              <div className="gate-subtitle">New here? Create your account.</div>
              <input type="text" placeholder="Your name" value={name} onChange={(e) => setName(e.target.value)} />
              <input type="email" placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} />
              <input type="password" placeholder="Choose a password (8+ characters)" value={password} onChange={(e) => setPassword(e.target.value)} />
              <button type="submit" disabled={busy || !name || !email || !password}>
                {busy ? 'Creating…' : 'Create account'}
              </button>
              {error && <div className="gate-error">{error}</div>}
            </form>
          )}
        </div>
      </div>
    )
  }

  return children
}
