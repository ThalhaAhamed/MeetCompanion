import { useEffect, useState } from 'react'
import { listImportableAgents, activateAgent } from './api'
import { InboxIcon } from './icons'
import EmptyState from './EmptyState'

export default function ImportAgents({ onClose, onImported }) {
  const [candidates, setCandidates] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [importingId, setImportingId] = useState(null)
  const [importError, setImportError] = useState(null)

  function load() {
    setLoading(true)
    setError(null)
    listImportableAgents()
      .then((d) => setCandidates(d.importable || []))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }

  useEffect(load, [])

  async function handleImport(agentConfigId) {
    setImportingId(agentConfigId)
    setImportError(null)
    try {
      await activateAgent(agentConfigId)
      onImported?.()
      onClose?.()
    } catch (e) {
      setImportError(`Failed to import: ${e.message}`)
    } finally {
      setImportingId(null)
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="launch-panel new-agent-panel" onClick={(e) => e.stopPropagation()}>
        <div className="launch-panel-head">
          <span>Import agent from MeetStream</span>
          <button type="button" className="launch-close" onClick={onClose}>×</button>
        </div>
        <p className="subtitle" style={{ marginTop: -4 }}>
          Agents created directly on your MeetStream account (or left behind by a removed member) that no one here has claimed yet.
        </p>

        {error && <div className="error">Failed to load: {error}</div>}
        {loading && <div className="loading">Loading…</div>}
        {importError && <div className="launch-error">{importError}</div>}

        {!loading && candidates && candidates.length === 0 && (
          <EmptyState icon={<InboxIcon />} title="Nothing to import" subtitle="Every agent on this account is already claimed." />
        )}

        {!loading && candidates && candidates.length > 0 && (
          <ul className="list" style={{ maxHeight: 360, overflowY: 'auto' }}>
            {candidates.map((a) => (
              <li key={a.AgentConfigID} className="list-item doc-item">
                <div className="list-item-title">{a.AgentName || 'Untitled agent'}</div>
                <div className="list-item-meta">
                  {a.Mode && <span className="tag">{a.Mode}</span>}
                  {a.Model?.provider && <span className="tag">{a.Model.provider}</span>}
                  <button
                    className="upload-btn"
                    onClick={() => handleImport(a.AgentConfigID)}
                    disabled={importingId === a.AgentConfigID}
                  >
                    {importingId === a.AgentConfigID ? 'Importing…' : 'Import'}
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
