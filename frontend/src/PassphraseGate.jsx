import { useEffect, useState } from 'react'
import { checkAuth, login } from './api'

export default function PassphraseGate({ children }) {
  const [status, setStatus] = useState('checking') // checking | locked | open
  const [passphrase, setPassphrase] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  function recheck() {
    checkAuth()
      .then((d) => setStatus(d.authenticated ? 'open' : 'locked'))
      .catch(() => setStatus('locked'))
  }

  useEffect(recheck, [])
  useEffect(() => {
    const onUnauthorized = () => setStatus('locked')
    window.addEventListener('hub:unauthorized', onUnauthorized)
    return () => window.removeEventListener('hub:unauthorized', onUnauthorized)
  }, [])

  async function submit(e) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await login(passphrase)
      setPassphrase('')
      setStatus('open')
    } catch (e) {
      setError('Incorrect passphrase.')
    } finally {
      setBusy(false)
    }
  }

  if (status === 'checking') {
    return <div className="gate-screen">Loading…</div>
  }

  if (status === 'locked') {
    return (
      <div className="gate-screen">
        <form className="gate-card" onSubmit={submit}>
          <div className="gate-title">MeetStream Companion</div>
          <div className="gate-subtitle">Enter the shared passphrase to open the hub.</div>
          <input
            type="password"
            autoFocus
            placeholder="Passphrase"
            value={passphrase}
            onChange={(e) => setPassphrase(e.target.value)}
          />
          <button type="submit" disabled={busy || !passphrase}>
            {busy ? 'Checking…' : 'Enter'}
          </button>
          {error && <div className="gate-error">{error}</div>}
        </form>
      </div>
    )
  }

  return children
}
