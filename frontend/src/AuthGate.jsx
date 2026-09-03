import { useEffect, useState } from 'react'
import { checkAuth, login, addMember, getBootstrapStatus } from './api'

export default function AuthGate({ children }) {
  const [status, setStatus] = useState('checking') // checking | locked | bootstrap | open
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const [passphrase, setPassphrase] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  function recheck() {
    checkAuth()
      .then((d) => {
        if (d.authenticated) {
          setStatus('open')
          return
        }
        getBootstrapStatus()
          .then((b) => setStatus(b.has_members ? 'locked' : 'bootstrap'))
          .catch(() => setStatus('locked'))
      })
      .catch(() => setStatus('locked'))
  }

  useEffect(recheck, [])
  useEffect(() => {
    const onUnauthorized = () => setStatus((s) => (s === 'open' ? 'locked' : s))
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

  async function submitBootstrap(e) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await addMember({ name, email, password, passphrase })
      await login(email, password)
      setPassword('')
      setStatus('open')
    } catch (e) {
      setError(e.message.includes('401') ? 'Incorrect passphrase.' : 'Could not create the account.')
    } finally {
      setBusy(false)
    }
  }

  if (status === 'checking') {
    return <div className="gate-screen">Loading…</div>
  }

  if (status === 'bootstrap') {
    return (
      <div className="gate-screen">
        <form className="gate-card" onSubmit={submitBootstrap}>
          <div className="gate-title">MeetStream Companion</div>
          <div className="gate-subtitle">No members yet — create the first account using the shared passphrase.</div>
          <input type="text" autoFocus placeholder="Your name" value={name} onChange={(e) => setName(e.target.value)} />
          <input type="email" placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} />
          <input type="password" placeholder="Choose a password (8+ characters)" value={password} onChange={(e) => setPassword(e.target.value)} />
          <input type="password" placeholder="Shared passphrase" value={passphrase} onChange={(e) => setPassphrase(e.target.value)} />
          <button type="submit" disabled={busy || !name || !email || !password || !passphrase}>
            {busy ? 'Creating…' : 'Create account'}
          </button>
          {error && <div className="gate-error">{error}</div>}
        </form>
      </div>
    )
  }

  if (status === 'locked') {
    return (
      <div className="gate-screen">
        <form className="gate-card" onSubmit={submitLogin}>
          <div className="gate-title">MeetStream Companion</div>
          <div className="gate-subtitle">Sign in to open the hub.</div>
          <input type="email" autoFocus placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} />
          <input type="password" placeholder="Password" value={password} onChange={(e) => setPassword(e.target.value)} />
          <button type="submit" disabled={busy || !email || !password}>
            {busy ? 'Signing in…' : 'Sign in'}
          </button>
          {error && <div className="gate-error">{error}</div>}
        </form>
      </div>
    )
  }

  return children
}
