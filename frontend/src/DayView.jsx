import { useEffect, useState, useCallback, useMemo, useRef } from 'react'
import { listMeetings, listDocuments, uploadDocument } from './api'
import MeetingDetail from './MeetingDetail'
import LaunchBot from './LaunchBot'
import EmptyState from './EmptyState'
import { UploadIcon, CalendarIcon, SearchIcon, InboxIcon, CursorClickIcon } from './icons'

function todayStr() {
  return new Date().toISOString().slice(0, 10)
}

const LIVE_STATUSES = new Set(['joining', 'in_meeting', 'recording', 'in_progress'])

export default function DayView() {
  const [day, setDay] = useState(todayStr())
  const [meetings, setMeetings] = useState([])
  const [documents, setDocuments] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [selectedMeetingId, setSelectedMeetingId] = useState(null)
  const [filterText, setFilterText] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState(null)
  const fileInputRef = useRef(null)

  const refresh = useCallback(() => {
    setLoading(true)
    setError(null)
    Promise.all([listMeetings(day), listDocuments(day)])
      .then(([m, d]) => {
        setMeetings(m)
        setDocuments(d)
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [day])

  useEffect(() => {
    setSelectedMeetingId(null)
    refresh()
  }, [day, refresh])

  function handleLaunched(meeting) {
    setDay(todayStr())
    refresh()
    setSelectedMeetingId(meeting.id)
  }

  async function handleFileChosen(e) {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    setUploading(true)
    setUploadError(null)
    try {
      await uploadDocument(file)
      refresh()
    } catch (e) {
      setUploadError(e.message)
    } finally {
      setUploading(false)
    }
  }

  const statuses = useMemo(() => {
    const s = new Set(meetings.map((m) => m.status))
    return ['all', ...Array.from(s)]
  }, [meetings])

  const filteredMeetings = useMemo(() => {
    const text = filterText.trim().toLowerCase()
    return meetings.filter((m) => {
      if (statusFilter !== 'all' && m.status !== statusFilter) return false
      if (!text) return true
      return [m.title, m.customer_name, m.project_name].some((v) => v?.toLowerCase().includes(text))
    })
  }, [meetings, filterText, statusFilter])

  const stats = useMemo(() => {
    const completed = meetings.filter((m) => m.status === 'completed').length
    const live = meetings.filter((m) => LIVE_STATUSES.has(m.status)).length
    return { total: meetings.length, completed, live }
  }, [meetings])

  return (
    <div className="app">
      <header className="topbar">
        <div>
          <h1>Day view</h1>
          <p className="subtitle">Meetings and documents captured on a given day.</p>
        </div>
        <div className="topbar-actions">
          <LaunchBot onLaunched={handleLaunched} />
          <label className="day-picker">
            <CalendarIcon className="day-picker-icon" />
            <input type="date" value={day} onChange={(e) => setDay(e.target.value)} />
          </label>
        </div>
      </header>

      {!loading && meetings.length > 0 && (
        <div className="stats-row">
          <div className="stat-pill">
            <span className="stat-value">{stats.total}</span>
            <span className="stat-label">Meetings</span>
          </div>
          <div className="stat-pill">
            <span className="stat-value stat-value-live">{stats.live}</span>
            <span className="stat-label">Live now</span>
          </div>
          <div className="stat-pill">
            <span className="stat-value stat-value-done">{stats.completed}</span>
            <span className="stat-label">Completed</span>
          </div>
          <div className="stat-pill">
            <span className="stat-value">{documents.length}</span>
            <span className="stat-label">Documents</span>
          </div>
        </div>
      )}

      {error && <div className="error">Failed to load: {error}</div>}
      {loading && (
        <div className="skeleton-list">
          <div className="skeleton-line" style={{ width: '40%' }} />
          <div className="skeleton-card" />
          <div className="skeleton-card" />
        </div>
      )}

      {!loading && (
        <div className="layout">
          <div className="column">
            <section>
              <div className="section-head">
                <h2>Meetings ({filteredMeetings.length}{filteredMeetings.length !== meetings.length ? ` / ${meetings.length}` : ''})</h2>
              </div>
              <div className="filter-row">
                <div className="filter-input-wrap">
                  <SearchIcon className="filter-input-icon" />
                  <input
                    type="text"
                    className="filter-input"
                    placeholder="Filter by title, customer, project…"
                    value={filterText}
                    onChange={(e) => setFilterText(e.target.value)}
                  />
                </div>
                <select className="filter-select" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
                  {statuses.map((s) => (
                    <option key={s} value={s}>{s === 'all' ? 'All statuses' : s}</option>
                  ))}
                </select>
              </div>
              {filteredMeetings.length === 0 && (
                <EmptyState
                  icon={<InboxIcon />}
                  title={meetings.length === 0 ? 'No meetings on this day' : 'No matches'}
                  subtitle={meetings.length === 0 ? 'Launch a bot into a call to see it show up here.' : 'Try a different filter or status.'}
                />
              )}
              <ul className="list">
                {filteredMeetings.map((m) => (
                  <li
                    key={m.id}
                    className={`list-item ${selectedMeetingId === m.id ? 'selected' : ''}`}
                    onClick={() => setSelectedMeetingId(m.id)}
                  >
                    <div className="list-item-title">{m.title || 'Untitled meeting'}</div>
                    <div className="list-item-meta">
                      <span className={`badge status-${m.status}`}>{m.status}</span>
                      {m.customer_name && <span className="tag">{m.customer_name}</span>}
                      {m.project_name && <span className="tag">{m.project_name}</span>}
                      {m.created_by_name && <span className="tag">by {m.created_by_name}</span>}
                      {m.started_at && (
                        <span className="time">{new Date(m.started_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            </section>

            <section>
              <div className="section-head">
                <h2>Documents ({documents.length})</h2>
                <button className="upload-btn" onClick={() => fileInputRef.current?.click()} disabled={uploading}>
                  <UploadIcon /> {uploading ? 'Uploading…' : 'Upload'}
                </button>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".pdf,.docx,.txt,.md,.csv"
                  onChange={handleFileChosen}
                  hidden
                />
              </div>
              {uploadError && <div className="error">Upload failed: {uploadError}</div>}
              {documents.length === 0 && (
                <EmptyState icon={<InboxIcon />} title="No documents indexed" subtitle="Upload a PDF, doc, or note to add it to company knowledge." />
              )}
              <ul className="list">
                {documents.map((d) => (
                  <li key={d.document_id} className="list-item doc-item">
                    <div className="list-item-title">{d.filename || 'Untitled document'}</div>
                    <div className="list-item-meta">
                      <span className="tag">{d.source_type}</span>
                      <span className="tag">{d.chunks_count} chunks</span>
                      {d.indexed_at && (
                        <span className="time">{new Date(d.indexed_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            </section>
          </div>

          <div className="column detail-column">
            {selectedMeetingId ? (
              <MeetingDetail meetingId={selectedMeetingId} />
            ) : (
              <EmptyState
                icon={<CursorClickIcon />}
                title="Select a meeting"
                subtitle="Its transcript, decisions, and action items will show up here."
              />
            )}
          </div>
        </div>
      )}
    </div>
  )
}
