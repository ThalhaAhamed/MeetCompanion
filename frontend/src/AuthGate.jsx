import { useEffect, useState } from 'react'
import { checkAuth, login, addMember, setMeetstreamApiKey } from './api'

export default function AuthGate({ children, onAuthenticated }) {
  const [status, setStatus] = useState('checking') // checking | gate | open
  const [mode, setMode] = useState('signin') // signin | signup
  const [workspaceMode, setWorkspaceMode] = useState('create') // create | join
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const [workspaceName, setWorkspaceName] = useState('')
  const [joinCode, setJoinCode] = useState('')
  const [meetstreamApiKey, setMeetstreamApiKeyInput] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  function recheck() {
    checkAuth()
      .then((d) => {
        if (d.authenticated && d.member) onAuthenticated?.(d.member)
        setStatus(d.authenticated ? 'open' : 'gate')
      })
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
      const d = await login(email, password)
      setPassword('')
      if (d.member) onAuthenticated?.(d.member)
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
      await addMember({
        name,
        email,
        password,
        workspace_name: workspaceMode === 'create' ? workspaceName : undefined,
        join_code: workspaceMode === 'join' ? joinCode : undefined,
      })
      const d = await login(email, password)
      setPassword('')
      if (d.member) onAuthenticated?.(d.member)
      // Best-effort: a missing/invalid key here shouldn't block getting into
      // the workspace - they can always set it later from Agent settings.
      if (meetstreamApiKey.trim()) {
        try {
          await setMeetstreamApiKey(meetstreamApiKey.trim())
        } catch {
          // ignore - not fatal to account creation
        }
      }
      setStatus('open')
    } catch (e) {
      setError(
        e.message.includes('409') ? 'That email is already a member — try signing in.'
        : e.message.includes('404') ? 'No workspace found with that join code.'
        : 'Could not create the account.'
      )
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
              <div className="gate-subtitle">Sign in to open your workspace.</div>
              <input type="email" autoFocus placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} />
              <input type="password" placeholder="Password" value={password} onChange={(e) => setPassword(e.target.value)} />
              <button type="submit" disabled={busy || !email || !password}>
                {busy ? 'Signing in…' : 'Sign in'}
              </button>
              {error && <div className="gate-error">{error}</div>}
              <div className="gate-subtitle" style={{ marginTop: -4 }}>Forgot your password? Ask any teammate to reset it for you from the Members page.</div>
            </form>
          ) : (
            <form onSubmit={submitSignup}>
              <div className="gate-subtitle">Every workspace is private — you'll only see meetings from the workspace you create or join.</div>
              <input type="text" placeholder="Your name" value={name} onChange={(e) => setName(e.target.value)} />
              <input type="email" placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} />
              <input type="password" placeholder="Choose a password (8+ characters)" value={password} onChange={(e) => setPassword(e.target.value)} />

              <div className="gate-tabs">
                <button type="button" className={workspaceMode === 'create' ? 'active' : ''} onClick={() => setWorkspaceMode('create')}>Create workspace</button>
                <button type="button" className={workspaceMode === 'join' ? 'active' : ''} onClick={() => setWorkspaceMode('join')}>Join workspace</button>
              </div>
              {workspaceMode === 'create' ? (
                <input type="text" placeholder="Workspace name (e.g. your team's name)" value={workspaceName} onChange={(e) => setWorkspaceName(e.target.value)} />
              ) : (
                <input type="text" placeholder="Join code (ask an existing member)" value={joinCode} onChange={(e) => setJoinCode(e.target.value)} />
              )}

              <input
                type="password"
                placeholder="Your MeetStream API key (optional - add later if you don't have one)"
                value={meetstreamApiKey}
                onChange={(e) => setMeetstreamApiKeyInput(e.target.value)}
              />
              <div className="gate-subtitle" style={{ marginTop: -4 }}>
                Your bots deploy under your own MeetStream account. You can skip this and add it later from Agent settings.
              </div>

              <button
                type="submit"
                disabled={busy || !name || !email || !password || (workspaceMode === 'create' ? !workspaceName : !joinCode)}
              >
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
