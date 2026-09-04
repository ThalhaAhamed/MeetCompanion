import { useState } from 'react'
import { searchMemory } from './api'

export default function MemorySearch() {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  async function submit(e) {
    e.preventDefault()
    if (!query.trim()) return
    setLoading(true)
    setError(null)
    try {
      const res = await searchMemory(query.trim(), { limit: 15 })
      setResults(res)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="app">
      <header className="topbar">
        <div>
          <h1>Search memory</h1>
          <p className="subtitle">Search across every indexed transcript, decision, and note — the same memory the in-meeting agent recalls from.</p>
        </div>
      </header>

      <form className="search-form" onSubmit={submit}>
        <input
          type="text"
          placeholder="e.g. what did we decide about pricing?"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          autoFocus
        />
        <button type="submit" disabled={loading || !query.trim()}>
          {loading ? 'Searching…' : 'Search'}
        </button>
      </form>

      {error && <div className="error">Search failed: {error}</div>}

      {results && (
        <div className="search-results">
          <h2>{results.total_results} result{results.total_results === 1 ? '' : 's'}</h2>
          {results.results.length === 0 ? (
            <p className="empty">No matches found.</p>
          ) : (
            <ul className="memories">
              {results.results.map((r) => (
                <li key={r.id} className="memory-item search-result">
                  <div className="list-item-meta">
                    <span className="badge">{r.memory_type || r.source_type}</span>
                    {r.meeting_title && <span className="tag">{r.meeting_title}</span>}
                    {r.meeting_date && <span className="tag">{r.meeting_date}</span>}
                    {r.project_name && <span className="tag">{r.project_name}</span>}
                    <span className="time">{(r.similarity * 100).toFixed(0)}% match</span>
                  </div>
                  <p>{r.content}</p>
                  {r.speaker && <span className="time">— {r.speaker}</span>}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}
