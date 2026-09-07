import { useEffect, useState } from 'react'
import { listImportableBots, importBot } from './api'
import { InboxIcon } from './icons'
import EmptyState from './EmptyState'

export default function ImportBots({ onClose, onImported }) {
  const [candidates, setCandidates] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [importingId, setImportingId] = useState(null)
  const [importedIds, setImportedIds] = useState(new Set())
  const [importError, setImportError] = useState(null)

  function load() {
    setLoading(true)
    setError(null)
    listImportableBots()
      .then((d) => setCandidates(d.importable || []))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }

  useEffect(load, [])

  async function handleImport(bot) {
    setImportingId(bot.bot_id)
    setImportError(null)
    try {
      const meeting = await importBot({
        bot_id: bot.bot_id,
        platform: bot.platform,
        meeting_url: bot.meeting_url,
        title: bot.bot_username ? `${bot.bot_username} (imported)` : undefined,
      })
      setImportedIds((s) => new Set(s).add(bot.bot_id))
      onImported?.(meeting)
    } catch (e) {
      setImportError(`Failed to import ${bot.bot_id}: ${e.message}`)
    } finally {
      setImportingId(null)
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="launch-panel new-agent-panel" onClick={(e) => e.stopPropagation()}>
        <div className="launch-panel-head">
          <span>Import old bot data</span>
          <button type="button" className="launch-close" onClick={onClose}>×</button>
        </div>
        <p className="subtitle" style={{ marginTop: -4 }}>
          Bots launched on your MeetStream account outside this app - importing pulls the transcript and runs it through the same memory extraction as a normal meeting.
        </p>

        {error && <div className="error">Failed to load: {error}</div>}
        {loading && <div className="loading">Loading…</div>}
        {importError && <div className="launch-error">{importError}</div>}

        {!loading && candidates && candidates.length === 0 && (
          <EmptyState icon={<InboxIcon />} title="Nothing to import" subtitle="Every bot on this account is already tracked here." />
        )}

        {!loading && candidates && candidates.length > 0 && (
          <ul className="list" style={{ maxHeight: 360, overflowY: 'auto' }}>
            {candidates.map((bot) => (
              <li key={bot.bot_id} className="list-item doc-item">
                <div className="list-item-title">{bot.bot_username || 'Untitled bot'}</div>
                <div className="list-item-meta">
                  {bot.meeting_url && <span className="tag">{bot.meeting_url}</span>}
                  {bot.platform && <span className="tag">{bot.platform}</span>}
                  {bot.status && <span className="tag">{bot.status}</span>}
                  {bot.start_time && <span className="time">{new Date(bot.start_time).toLocaleString()}</span>}
                  {importedIds.has(bot.bot_id) ? (
                    <span className="badge status-completed">Imported</span>
                  ) : (
                    <button
                      className="upload-btn"
                      onClick={() => handleImport(bot)}
                      disabled={importingId === bot.bot_id}
                    >
                      {importingId === bot.bot_id ? 'Importing…' : 'Import'}
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
