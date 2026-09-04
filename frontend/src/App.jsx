import { useEffect, useState } from 'react'
import DayView from './DayView'
import AgentSettings from './AgentSettings'
import MemorySearch from './MemorySearch'
import Members from './Members'
import AuthGate from './AuthGate'
import { checkAuth, logout, getAgentCredentials, setMeetstreamApiKey, clearMeetstreamApiKey } from './api'
import './App.css'

const ICONS = {
  day: (
    <svg viewBox="0 0 18 18" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.6">
      <rect x="2" y="2" width="14" height="14" rx="3" />
      <path d="M2 7h14M6.5 2v3.2M11.5 2v3.2" strokeLinecap="round" />
    </svg>
  ),
  search: (
    <svg viewBox="0 0 18 18" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.6">
      <circle cx="8" cy="8" r="5.2" />
      <path d="M15.5 15.5L12 12" strokeLinecap="round" />
    </svg>
  ),
  agent: (
    <svg viewBox="0 0 18 18" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.6">
      <rect x="3" y="5.5" width="12" height="9" rx="3" />
      <path d="M9 2.5v3M6.5 9.5v1M11.5 9.5v1" strokeLinecap="round" />
    </svg>
  ),
  members: (
    <svg viewBox="0 0 18 18" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.6">
      <circle cx="6.5" cy="6" r="2.4" />
      <path d="M2.2 15c0-2.4 1.9-4.3 4.3-4.3s4.3 1.9 4.3 4.3" strokeLinecap="round" />
      <circle cx="13" cy="6.5" r="1.9" />
      <path d="M11.5 10.9c1.9.2 3.4 1.9 3.4 4" strokeLinecap="round" />
    </svg>
  ),
}

const PAGES = {
  day: { label: 'Day view', Component: DayView },
  search: { label: 'Search memory', Component: MemorySearch },
  agent: { label: 'Agent', Component: AgentSettings },
  members: { label: 'Members', Component: Members },
}

export default function App() {
  const [page, setPage] = useState('day')
  const [me, setMe] = useState(null)
  const Page = PAGES[page].Component

  useEffect(() => {
    checkAuth().then((d) => d.member && setMe(d.member)).catch(() => {})
  }, [])

  async function handleSignOut() {
    await logout().catch(() => {})
    window.location.reload()
  }

  return (
    <AuthGate>
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">
            <svg xmlns="http://www.w3.org/2000/svg" width="34" height="34" viewBox="0 0 32 32">
              <rect x="0.478505" y="0.478505" width="31.043" height="31.043" rx="5.5215" fill="#FD6316" />
              <path d="M7.1756 26.1754C6.42952 26.1754 5.82471 25.5705 5.82471 24.8245V16.2688C5.82471 15.5227 6.42952 14.9179 7.1756 14.9179H15.7313C16.4774 14.9179 17.0822 15.5227 17.0822 16.2688V24.8245C17.0822 25.5705 16.4774 26.1754 15.7313 26.1754H7.1756Z" fill="white" />
              <path d="M18.7118 14.8007C17.834 14.9138 17.0864 14.1662 17.1994 13.2883L18.0847 6.41461C18.1564 5.8583 18.8357 5.62666 19.2323 6.02328L25.9769 12.7679C26.3735 13.1645 26.1418 13.8438 25.5855 13.9154L18.7118 14.8007Z" fill="white" />
            </svg>
          </span>
          <span className="brand-name">MeetStream <span className="brand-sub">Companion</span></span>
        </div>

        <div className="nav-group-label">Workspace</div>
        <nav className="nav">
          {Object.entries(PAGES).map(([key, { label }]) => (
            <div
              key={key}
              className={`nav-item ${page === key ? 'active' : ''}`}
              onClick={() => setPage(key)}
            >
              <span className="nav-icon">{ICONS[key]}</span> {label}
            </div>
          ))}
        </nav>

        {me && (
          <div className="sidebar-footer">
            <div className="sidebar-user">
              <div className="sidebar-user-name">{me.name || me.email}</div>
              <div className="sidebar-user-email">{me.email}</div>
            </div>
            <ApiKeyControl />
            <button className="sidebar-signout" onClick={handleSignOut}>Sign out</button>
          </div>
        )}
      </aside>

      <Page />
    </div>
    </AuthGate>
  )
}

function ApiKeyControl() {
  const [credentials, setCredentials] = useState(null)
  const [error, setError] = useState(null)
  const [editing, setEditing] = useState(false)
  const [input, setInput] = useState('')
  const [saving, setSaving] = useState(false)

  function load() {
    getAgentCredentials().catch((e) => setError(e.message)).then((d) => d && setCredentials(d))
  }

  useEffect(load, [])

  async function save(e) {
    e.preventDefault()
    if (!input.trim()) return
    setSaving(true)
    setError(null)
    try {
      await setMeetstreamApiKey(input.trim())
      setInput('')
      setEditing(false)
      load()
    } catch (e) {
      setError(e.message)
    } finally {
      setSaving(false)
    }
  }

  async function remove() {
    setSaving(true)
    setError(null)
    try {
      await clearMeetstreamApiKey()
      load()
    } catch (e) {
      setError(e.message)
    } finally {
      setSaving(false)
    }
  }

  const key = credentials?.meetstream_api_key

  return (
    <div className="sidebar-api-key">
      <div className="sidebar-api-key-head">
        <span>MeetStream API key</span>
        {key && !editing && (
          <button className="link-btn" onClick={() => setEditing(true)}>
            {key.is_personal ? 'Change' : 'Add your own'}
          </button>
        )}
      </div>
      {!editing && key && (
        <div className="sidebar-api-key-value">
          {key.configured ? key.masked_value : 'Not configured'}
          <span className="tag">{key.is_personal ? 'your key' : 'shared default'}</span>
        </div>
      )}
      {editing && (
        <form className="sidebar-api-key-form" onSubmit={save}>
          <input
            type="password"
            autoFocus
            placeholder="Paste your MeetStream API key"
            value={input}
            onChange={(e) => setInput(e.target.value)}
          />
          <div className="sidebar-api-key-actions">
            <button type="submit" disabled={saving || !input.trim()}>{saving ? 'Saving…' : 'Save'}</button>
            <button type="button" onClick={() => { setEditing(false); setInput('') }} disabled={saving}>Cancel</button>
            {key?.is_personal && (
              <button type="button" onClick={remove} disabled={saving}>Remove</button>
            )}
          </div>
        </form>
      )}
      {error && <div className="error">{error}</div>}
    </div>
  )
}
