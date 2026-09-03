import { useState } from 'react'
import DayView from './DayView'
import AgentSettings from './AgentSettings'
import MemorySearch from './MemorySearch'
import './App.css'

const ICONS = {
  day: (
    <svg viewBox="0 0 18 18" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.6">
      <rect x="2" y="2" width="14" height="14" rx="3" />
      <path d="M2 7h14M6.5 2v3.2M11.5 2v3.2" strokeLinecap="round" />
    </svg>
  ),
  search: (
    <svg viewBox="0 0 18 18" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.6">
      <circle cx="8" cy="8" r="5.2" />
      <path d="M15.5 15.5L12 12" strokeLinecap="round" />
    </svg>
  ),
  agent: (
    <svg viewBox="0 0 18 18" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.6">
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
            <svg viewBox="0 0 24 24" width="20" height="20" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M6 2.5h9.5L20 7v13a1.5 1.5 0 0 1-1.5 1.5h-11A1.5 1.5 0 0 1 6 20V4a1.5 1.5 0 0 1 0-1.5Z" fill="#fff" />
              <path d="M15.5 2.5V6a1 1 0 0 0 1 1H20" fill="#f97316" />
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
      </aside>

      <Page />
    </div>
  )
}
