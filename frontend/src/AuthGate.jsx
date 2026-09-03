import { useEffect, useState } from 'react'
import { checkAuth, login } from './api'

export default function AuthGate({ children }) {
  const [status, setStatus] = useState('checking') // checking | gate | open
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
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

  if (status === 'checking') {
    return <div className="gate-screen">Loading…</div>
  }

  if (status === 'gate') {
    return (
      <div className="gate-screen">
        <div className="gate-card">
          <div className="gate-title">MeetStream Companion</div>
          <form onSubmit={submitLogin}>
            <div className="gate-subtitle">Sign in to open the hub. Don't have an account? Ask an existing member to add you.</div>
            <input type="email" autoFocus placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} />
            <input type="password" placeholder="Password" value={password} onChange={(e) => setPassword(e.target.value)} />
            <button type="submit" disabled={busy || !email || !password}>
              {busy ? 'Signing in…' : 'Sign in'}
            </button>
            {error && <div className="gate-error">{error}</div>}
          </form>
        </div>
      </div>
    )
  }

  return children
}
