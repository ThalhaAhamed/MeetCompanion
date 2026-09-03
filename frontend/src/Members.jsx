import { useEffect, useState } from 'react'
import { listMembers, addMember, removeMember, checkAuth, getWorkspace } from './api'
import EmptyState from './EmptyState'
import { InboxIcon } from './icons'

export default function Members() {
  const [members, setMembers] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [self, setSelf] = useState(null)
  const [workspace, setWorkspace] = useState(null)

  const [showForm, setShowForm] = useState(false)
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [formError, setFormError] = useState(null)
  const [removingId, setRemovingId] = useState(null)

  function load() {
    setLoading(true)
    setError(null)
    listMembers()
      .then((d) => setMembers(d.members || []))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
    checkAuth().then((d) => d.member && setSelf(d.member))
    getWorkspace().then(setWorkspace).catch(() => {})
  }

  useEffect(load, [])

  async function submit(e) {
    e.preventDefault()
    setBusy(true)
    setFormError(null)
    try {
      // Members are already signed in here, so no passphrase is needed -
      // that's only for creating the very first account at the gate.
      await addMember({ name, email, password })
      setName('')
      setEmail('')
      setPassword('')
      setShowForm(false)
      load()
    } catch (e) {
      setFormError(e.message.includes('409') ? 'That email is already a member.' : 'Could not add member.')
    } finally {
      setBusy(false)
    }
  }

  async function handleRemove(id) {
    setRemovingId(id)
    try {
      await removeMember(id)
      load()
    } catch (e) {
      setError(e.message)
    } finally {
      setRemovingId(null)
    }
  }

  return (
    <div className="app">
      <header className="topbar">
        <div>
          <h1>Members</h1>
          <p className="subtitle">
            {workspace ? `Everyone in "${workspace.name}".` : 'Everyone who can sign into this workspace.'}
          </p>
        </div>
        <div className="topbar-actions">
          <button className="launch-btn" onClick={() => setShowForm((v) => !v)}>
            + Add member
          </button>
        </div>
      </header>

      {workspace && (
        <div className="empty-state" style={{ padding: '14px 18px', marginBottom: 20, alignItems: 'flex-start', textAlign: 'left' }}>
          <div className="list-item-title" style={{ marginBottom: 4 }}>Invite people to this workspace</div>
          <p className="subtitle" style={{ margin: 0 }}>
            Share this join code — anyone can use it on the "Create account" screen to join this same workspace: <span className="tag">{workspace.join_code}</span>
          </p>
        </div>
      )}

      {showForm && (
        <form className="launch-panel new-agent-panel" onSubmit={submit} style={{ maxWidth: 380 }}>
          <div className="launch-panel-head">
            <span>Add a member</span>
            <button type="button" className="launch-close" onClick={() => setShowForm(false)}>×</button>
          </div>
          <input type="text" placeholder="Name" value={name} onChange={(e) => setName(e.target.value)} required />
          <input type="email" placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} required />
          <input type="password" placeholder="Temporary password (8+ characters)" value={password} onChange={(e) => setPassword(e.target.value)} required />
          <button type="submit" disabled={busy || !name || !email || password.length < 8}>
            {busy ? 'Adding…' : 'Add member'}
          </button>
          {formError && <div className="launch-error">{formError}</div>}
        </form>
      )}

      {error && <div className="error">Failed to load members: {error}</div>}
      {loading && <div className="loading">Loading…</div>}
      {!loading && members.length === 0 && (
        <EmptyState icon={<InboxIcon />} title="No members" subtitle="Add someone to get started." />
      )}

      <ul className="list">
        {members.map((m) => (
          <li key={m.id} className="list-item doc-item">
            <div className="list-item-title">{m.name || m.email}{self?.id === m.id ? ' (you)' : ''}</div>
            <div className="list-item-meta">
              <span className="tag">{m.email}</span>
              {members.length > 1 && (
                <button
                  className="upload-btn"
                  onClick={() => handleRemove(m.id)}
                  disabled={removingId === m.id}
                >
                  {removingId === m.id ? 'Removing…' : 'Remove'}
                </button>
              )}
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}
