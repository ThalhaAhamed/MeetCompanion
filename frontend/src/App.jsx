import { useState } from 'react'
import DayView from './DayView'
import AgentSettings from './AgentSettings'
import MemorySearch from './MemorySearch'
import './App.css'

const PAGES = {
  day: { label: 'Day view', icon: '▦', Component: DayView },
  search: { label: 'Search memory', icon: '⌕', Component: MemorySearch },
  agent: { label: 'Agent', icon: '◈', Component: AgentSettings },
}

export default function App() {
  const [page, setPage] = useState('day')
  const Page = PAGES[page].Component

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
          {Object.entries(PAGES).map(([key, { label, icon }]) => (
            <div
              key={key}
              className={`nav-item ${page === key ? 'active' : ''}`}
              onClick={() => setPage(key)}
            >
              <span className="nav-icon">{icon}</span> {label}
            </div>
          ))}
        </nav>
      </aside>

      <Page />
    </div>
  )
}
