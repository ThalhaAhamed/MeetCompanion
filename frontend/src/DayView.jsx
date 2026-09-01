import { useEffect, useState, useCallback } from 'react'
import { listMeetings, listDocuments } from './api'
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
            <h2>Meetings ({meetings.length})</h2>
            {meetings.length === 0 && !loading && <p className="empty">No meetings on this day.</p>}
            <ul className="list">
              {meetings.map((m) => (
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
            <h2>Documents ({documents.length})</h2>
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
