import { useEffect, useMemo, useState } from 'react'
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
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')

  function load() {
    setLoading(true)
    setError(null)
    listImportableBots()
      .then((d) => setCandidates(d.importable || []))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }

  useEffect(load, [])

  const statusOptions = useMemo(() => {
    const set = new Set((candidates || []).map((b) => b.status).filter(Boolean))
    return Array.from(set).sort()
  }, [candidates])

  const hasActiveFilters = Boolean(search.trim()) || statusFilter !== 'all' || dateFrom || dateTo

  function clearFilters() {
    setSearch('')
    setStatusFilter('all')
    setDateFrom('')
    setDateTo('')
  }

  const filteredCandidates = useMemo(() => {
    if (!candidates) return candidates
    const q = search.trim().toLowerCase()
    const fromTs = dateFrom ? new Date(dateFrom).getTime() : null
    const toTs = dateTo ? new Date(dateTo).getTime() + 24 * 60 * 60 * 1000 - 1 : null
    return candidates.filter((bot) => {
      if (statusFilter !== 'all' && bot.status !== statusFilter) return false
      if (fromTs || toTs) {
        const ts = bot.start_time ? new Date(bot.start_time).getTime() : null
        if (ts === null || Number.isNaN(ts)) return false
        if (fromTs && ts < fromTs) return false
        if (toTs && ts > toTs) return false
      }
      if (q) {
        const haystack = `${bot.bot_username || ''} ${bot.meeting_url || ''}`.toLowerCase()
        if (!haystack.includes(q)) return false
      }
      return true
    })
  }, [candidates, search, statusFilter, dateFrom, dateTo])

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
      <div className="launch-panel new-agent-panel import-bots-panel" onClick={(e) => e.stopPropagation()}>
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

        {!loading && candidates && candidates.length > 0 && (
          <div className="import-filters">
            <div className="import-filter-search">
              <svg viewBox="0 0 20 20" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="1.6">
                <circle cx="8.5" cy="8.5" r="6" />
                <line x1="13" y1="13" x2="18" y2="18" strokeLinecap="round" />
              </svg>
              <input
                type="text"
                placeholder="Search bot name or meeting URL…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
              {search && (
                <button type="button" className="import-filter-clear-inline" onClick={() => setSearch('')} aria-label="Clear search">×</button>
              )}
            </div>

            <div className="import-filter-row">
              {statusOptions.length > 1 && (
                <div className="import-filter-field">
                  <label>Status</label>
                  <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
                    <option value="all">Any</option>
                    {statusOptions.map((s) => (
                      <option key={s} value={s}>{s}</option>
                    ))}
                  </select>
                </div>
              )}
              <div className="import-filter-field">
                <label>From</label>
                <input type="date" value={dateFrom} max={dateTo || undefined} onChange={(e) => setDateFrom(e.target.value)} />
              </div>
              <div className="import-filter-field">
                <label>To</label>
                <input type="date" value={dateTo} min={dateFrom || undefined} onChange={(e) => setDateTo(e.target.value)} />
              </div>
              {hasActiveFilters && (
                <button type="button" className="import-filter-clear" onClick={clearFilters}>Clear filters</button>
              )}
            </div>
          </div>
        )}

        {!loading && candidates && candidates.length === 0 && (
          <EmptyState icon={<InboxIcon />} title="Nothing to import" subtitle="Every bot on this account is already tracked here." />
        )}

        {!loading && candidates && candidates.length > 0 && filteredCandidates.length === 0 && (
          <EmptyState icon={<InboxIcon />} title="No matches" subtitle="Try a different search or filter." />
        )}

        {!loading && candidates && filteredCandidates.length > 0 && (
          <>
            {hasActiveFilters && (
              <div className="import-result-count">{filteredCandidates.length} of {candidates.length} bots</div>
            )}
            <ul className="list import-bot-list">
              {filteredCandidates.map((bot) => (
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
          </>
        )}
      </div>
    </div>
  )
}
