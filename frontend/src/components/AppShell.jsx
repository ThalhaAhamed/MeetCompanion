import { useEffect, useState } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import Logo from './Logo'
import {
  AskAiIcon,
  DashboardIcon,
  MeetingsIcon,
  MembersIcon,
  MoonIcon,
  NotebookIcon,
  SearchIcon,
  SettingsIcon,
  SidebarIcon,
  SunIcon,
} from './Icons'

const PRIMARY_NAV = [
  { to: '/', label: 'Dashboard', Icon: DashboardIcon, end: true },
  { to: '/meetings', label: 'Meetings', Icon: MeetingsIcon },
  { to: '/notebook', label: 'Notebook', Icon: NotebookIcon },
  { to: '/ask', label: 'Ask AI', Icon: AskAiIcon },
]

const SECONDARY_NAV = [
  { to: '/members', label: 'Members', Icon: MembersIcon },
  { to: '/settings', label: 'Settings', Icon: SettingsIcon },
]

const THEME_KEY = 'meet-companion:theme'
const COLLAPSE_KEY = 'meet-companion:sidebar-collapsed'

export function useTheme() {
  const [theme, setTheme] = useState(() => {
    if (typeof window === 'undefined') return 'light'
    const stored = window.localStorage.getItem(THEME_KEY)
    if (stored) return stored
    return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  })

  useEffect(() => {
    document.documentElement.classList.toggle('dark', theme === 'dark')
    try {
      window.localStorage.setItem(THEME_KEY, theme)
    } catch {
      // Private browsing can reject writes; the theme still applies this session.
    }
  }, [theme])

  return [theme, () => setTheme((t) => (t === 'dark' ? 'light' : 'dark'))]
}

function initialsOf(user) {
  const source = user?.name || user?.email || '?'
  return source
    .split(/[\s@._-]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0].toUpperCase())
    .join('')
}

function NavSection({ items, collapsed }) {
  return (
    <nav className="flex flex-col gap-1">
      {items.map(({ to, label, Icon, end }) => (
        <NavLink
          key={to}
          to={to}
          end={end}
          className={`mc-nav-item ${collapsed ? 'justify-center px-0' : ''}`}
          title={collapsed ? label : undefined}
        >
          <Icon size={18} />
          {!collapsed && <span>{label}</span>}
        </NavLink>
      ))}
    </nav>
  )
}

function Avatar({ user, size = 34 }) {
  return (
    <div
      className="flex items-center justify-center rounded-full text-xs font-semibold"
      style={{
        width: size,
        height: size,
        background: 'linear-gradient(135deg, var(--color-brand-400), var(--color-brand-700))',
        color: '#fff',
      }}
      aria-hidden="true"
    >
      {initialsOf(user)}
    </div>
  )
}

export default function AppShell({ user, onSignOut, children }) {
  const [theme, toggleTheme] = useTheme()
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const [collapsed, setCollapsed] = useState(() => {
    try {
      return window.localStorage.getItem(COLLAPSE_KEY) === 'true'
    } catch {
      return false
    }
  })

  useEffect(() => {
    try {
      window.localStorage.setItem(COLLAPSE_KEY, String(collapsed))
    } catch {
      // Non-critical preference.
    }
  }, [collapsed])

  function submitSearch(event) {
    event.preventDefault()
    if (!query.trim()) return
    navigate(`/notebook?q=${encodeURIComponent(query.trim())}`)
  }

  return (
    <div className="flex min-h-screen" style={{ backgroundColor: 'var(--surface-page)' }}>
      <aside
        className="hidden md:flex flex-col shrink-0 transition-[width] duration-200"
        style={{
          width: collapsed ? '5rem' : '16rem',
          backgroundColor: 'var(--surface-nav)',
          borderRight: '1px solid var(--border-subtle)',
        }}
      >
        <div className={`flex items-center h-[4.5rem] px-5 ${collapsed ? 'justify-center px-0' : ''}`}>
          {collapsed ? <Logo variant="icon" size={32} /> : <Logo size={32} />}
        </div>

        <div className="flex-1 overflow-y-auto mc-scroll px-3 py-2">
          {!collapsed && (
            <div
              className="px-3 pb-2 text-[0.65rem] font-semibold uppercase tracking-[0.14em]"
              style={{ color: 'var(--text-faint)' }}
            >
              Workspace
            </div>
          )}
          <NavSection items={PRIMARY_NAV} collapsed={collapsed} />

          {!collapsed && (
            <div
              className="mt-6 px-3 pb-2 text-[0.65rem] font-semibold uppercase tracking-[0.14em]"
              style={{ color: 'var(--text-faint)' }}
            >
              Manage
            </div>
          )}
          <div className={collapsed ? 'mt-4' : ''}>
            <NavSection items={SECONDARY_NAV} collapsed={collapsed} />
          </div>
        </div>

        <div className="p-3">
          <button
            type="button"
            className={`mc-btn mc-btn-ghost w-full ${collapsed ? 'px-0' : ''}`}
            onClick={() => setCollapsed((c) => !c)}
            title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            <SidebarIcon size={17} />
            {!collapsed && <span>Collapse</span>}
          </button>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header
          className="sticky top-0 z-30 flex h-[4.5rem] items-center gap-3 px-5 md:px-8"
          style={{
            backgroundColor: 'var(--surface-nav)',
            borderBottom: '1px solid var(--border-subtle)',
          }}
        >
          <div className="md:hidden">
            <Logo variant="icon" size={30} />
          </div>

          <form className="mc-search hidden max-w-md flex-1 sm:flex" onSubmit={submitSearch}>
            <SearchIcon size={17} />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search your notes…"
              aria-label="Search your notes"
            />
          </form>

          <div className="ml-auto flex items-center gap-2">
            <button
              type="button"
              className="mc-btn mc-btn-ghost px-2.5"
              onClick={toggleTheme}
              title={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
              aria-label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
            >
              {theme === 'dark' ? <SunIcon size={18} /> : <MoonIcon size={18} />}
            </button>

            {user && (
              <div className="flex items-center gap-3 pl-1">
                <div className="hidden text-right leading-tight lg:block">
                  <div className="text-sm font-semibold" style={{ color: 'var(--text-strong)' }}>
                    {user.name || user.email}
                  </div>
                  <button
                    type="button"
                    className="text-xs hover:underline"
                    style={{ color: 'var(--text-faint)' }}
                    onClick={onSignOut}
                  >
                    Sign out
                  </button>
                </div>
                <Avatar user={user} />
              </div>
            )}
          </div>
        </header>

        <main className="min-w-0 flex-1 pb-24 md:pb-0">{children}</main>
      </div>

      {/* Small screens swap the sidebar for a bottom bar */}
      <nav
        className="md:hidden fixed bottom-0 inset-x-0 z-40 flex justify-around py-2"
        style={{
          backgroundColor: 'var(--surface-nav)',
          borderTop: '1px solid var(--border-subtle)',
        }}
      >
        {PRIMARY_NAV.concat(SECONDARY_NAV.slice(-1)).map(({ to, label, Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className="mc-nav-item flex-col gap-0.5 px-3 py-1.5 text-[0.65rem]"
            aria-label={label}
          >
            <Icon size={19} />
            <span>{label}</span>
          </NavLink>
        ))}
      </nav>
    </div>
  )
}

export function PageHeader({ title, description, actions }) {
  return (
    <header className="flex flex-wrap items-start justify-between gap-4 mb-6">
      <div className="min-w-0">
        <h1 className="text-[1.6rem] font-semibold leading-tight">{title}</h1>
        {description && (
          <p className="mt-1.5 text-sm" style={{ color: 'var(--text-muted)' }}>
            {description}
          </p>
        )}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </header>
  )
}

export function Page({ children }) {
  return <div className="mx-auto w-full max-w-[1500px] px-5 py-6 md:px-8 md:py-7">{children}</div>
}
