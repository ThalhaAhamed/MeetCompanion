import { useState } from 'react'
import DayView from './DayView'
import AgentSettings from './AgentSettings'
import './App.css'

export default function App() {
  const [page, setPage] = useState('day')

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" xmlns="http://www.w3.org/2000/svg">
              <rect x="2" y="2" width="13" height="13" rx="4" fill="#fff" />
              <rect x="9" y="9" width="13" height="13" rx="4" fill="#fff" fillOpacity="0.55" />
            </svg>
          </span>
          <span className="brand-name">MeetStream <span className="brand-sub">Companion</span></span>
        </div>
        <nav className="nav">
          <div className={`nav-item ${page === 'day' ? 'active' : ''}`} onClick={() => setPage('day')}>
            <span className="nav-icon">▦</span> Day view
          </div>
          <div className={`nav-item ${page === 'agent' ? 'active' : ''}`} onClick={() => setPage('agent')}>
            <span className="nav-icon">◈</span> Agent
          </div>
        </nav>
      </aside>

      {page === 'day' ? <DayView /> : <AgentSettings />}
    </div>
  )
}
