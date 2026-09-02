import { useState } from 'react'
import DayView from './DayView'
import AgentSettings from './AgentSettings'
import MemorySearch from './MemorySearch'
import './App.css'

const ICONS = {
  day: (
    <svg viewBox="0 0 18 18" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.6">
      <rect x="2" y="2" width="14" height="14" rx="3" />
      <path d="M2 7h14M6.5 2v3.2M11.5 2v3.2" strokeLinecap="round" />
    </svg>
  ),
  search: (
    <svg viewBox="0 0 18 18" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.6">
      <circle cx="8" cy="8" r="5.2" />
      <path d="M15.5 15.5L12 12" strokeLinecap="round" />
    </svg>
  ),
  agent: (
    <svg viewBox="0 0 18 18" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.6">
      <rect x="3" y="5.5" width="12" height="9" rx="3" />
      <path d="M9 2.5v3M6.5 9.5v1M11.5 9.5v1" strokeLinecap="round" />
    </svg>
  ),
}

const PAGES = {
  day: { label: 'Day view', Component: DayView },
  search: { label: 'Search memory', Component: MemorySearch },
  agent: { label: 'Agent', Component: AgentSettings },
}

export default function App() {
  const [page, setPage] = useState('day')
  const Page = PAGES[page].Component

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" xmlns="http://www.w3.org/2000/svg">
              <rect x="2" y="2" width="13" height="13" rx="4" fill="#fff" />
              <rect x="9" y="9" width="13" height="13" rx="4" fill="#fff" fillOpacity="0.55" />
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

        <div className="sidebar-footer">
          <div className="sidebar-footer-label">Environment</div>
          <div className="sidebar-footer-value">Local development</div>
        </div>
      </aside>

      <Page />
    </div>
  )
}
