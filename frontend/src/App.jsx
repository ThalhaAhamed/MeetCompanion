import { useCallback, useEffect, useState } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import AppShell from './components/AppShell'
import { Loading } from './components/ui'
import Onboarding from './pages/Onboarding'
import SignIn from './pages/SignIn'
import Dashboard from './pages/Dashboard'
import Notebook from './pages/Notebook'
import AskAi from './pages/AskAi'
import Graph from './pages/Graph'
import Meetings from './pages/Meetings'
import Members from './pages/Members'
import Agent from './pages/Agent'
import Settings from './pages/Settings'
import { checkAuth, getSetupStatus, logout } from './api'

/**
 * Boot sequence: decide whether the user needs setup, sign-in, or the app.
 *
 * Setup is checked first because it must be reachable before any account
 * exists - a fresh install has no user to authenticate.
 */
export default function App() {
  const [phase, setPhase] = useState('loading')
  const [user, setUser] = useState(null)

  const boot = useCallback(async () => {
    setPhase('loading')
    try {
      const status = await getSetupStatus()
      if (status.needs_setup) {
        setPhase('onboarding')
        return
      }
    } catch {
      // A 401 here means setup is already complete and locked down, which is
      // itself the answer: carry on to authentication.
    }

    try {
      // /auth/check answers 200 with authenticated:false when signed out, so
      // a successful response is not on its own proof of a session.
      const result = await checkAuth()
      if (result?.authenticated && result.member) {
        setUser(result.member)
        setPhase('ready')
      } else {
        setPhase('signin')
      }
    } catch {
      setPhase('signin')
    }
  }, [])

  useEffect(() => {
    boot()
  }, [boot])

  useEffect(() => {
    function onUnauthorized() {
      setUser(null)
      setPhase('signin')
    }
    window.addEventListener('hub:unauthorized', onUnauthorized)
    return () => window.removeEventListener('hub:unauthorized', onUnauthorized)
  }, [])

  async function handleSignOut() {
    await logout().catch(() => {})
    setUser(null)
    setPhase('signin')
  }

  if (phase === 'loading') {
    return (
      <div className="flex min-h-screen items-center justify-center" style={{ backgroundColor: 'var(--surface-page)' }}>
        <Loading label="Starting Meet Companion…" />
      </div>
    )
  }

  if (phase === 'onboarding') return <Onboarding onComplete={boot} />
  if (phase === 'signin') return <SignIn onSignedIn={boot} />

  return (
    <AppShell user={user} onSignOut={handleSignOut}>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/meetings" element={<Meetings />} />
        <Route path="/meetings/:meetingId" element={<Meetings />} />
        <Route path="/notebook" element={<Notebook />} />
        <Route path="/notebook/:noteId" element={<Notebook />} />
        <Route path="/ask" element={<AskAi />} />
        <Route path="/graph" element={<Graph />} />
        <Route path="/agent" element={<Agent />} />
        <Route path="/members" element={<Members />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AppShell>
  )
}
