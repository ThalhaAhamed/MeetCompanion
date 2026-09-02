import { useEffect, useState, useCallback, useMemo, useRef } from 'react'
import { listMeetings, listDocuments, uploadDocument } from './api'
import MeetingDetail from './MeetingDetail'
import LaunchBot from './LaunchBot'

function todayStr() {
  return new Date().toISOString().slice(0, 10)
}

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
            <span>Day</span>
            <input type="date" value={day} onChange={(e) => setDay(e.target.value)} />
          </label>
        </div>
      </header>

      {error && <div className="error">Failed to load: {error}</div>}
      {loading && <div className="loading">Loading…</div>}

      <div className="layout">
        <div className="column">
          <section>
            <div className="section-head">
              <h2>Meetings ({filteredMeetings.length}{filteredMeetings.length !== meetings.length ? ` / ${meetings.length}` : ''})</h2>
            </div>
            <div className="filter-row">
              <input
                type="text"
                className="filter-input"
                placeholder="Filter by title, customer, project…"
                value={filterText}
                onChange={(e) => setFilterText(e.target.value)}
              />
              <select className="filter-select" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
                {statuses.map((s) => (
                  <option key={s} value={s}>{s === 'all' ? 'All statuses' : s}</option>
                ))}
              </select>
            </div>
            {filteredMeetings.length === 0 && !loading && (
              <p className="empty">{meetings.length === 0 ? 'No meetings on this day.' : 'No meetings match this filter.'}</p>
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
                {uploading ? 'Uploading…' : '+ Upload'}
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
            {documents.length === 0 && !loading && <p className="empty">No documents indexed on this day.</p>}
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
            <div className="placeholder">Select a meeting to see its transcript, decisions, and action items.</div>
          )}
        </div>
      </div>
    </div>
  )
}
