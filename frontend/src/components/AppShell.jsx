import { useEffect, useState } from 'react'
import { NavLink } from 'react-router-dom'
import Logo from './Logo'
import {
  AskAiIcon,
  DashboardIcon,
  MeetingsIcon,
  MembersIcon,
  MoonIcon,
  NotebookIcon,
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
      // Private browsing can reject writes; the theme still applies for this session.
    }
  }, [theme])

  return [theme, () => setTheme((t) => (t === 'dark' ? 'light' : 'dark'))]
}

function NavSection({ items, collapsed }) {
  return (
    <nav className="flex flex-col gap-1">
      {items.map(({ to, label, Icon, end }) => (
        <NavLink
          key={to}
          to={to}
          end={end}
          className="mc-nav-item"
          title={collapsed ? label : undefined}
        >
          <Icon size={18} />
          {!collapsed && <span>{label}</span>}
        </NavLink>
      ))}
    </nav>
  )
}

export default function AppShell({ user, onSignOut, children }) {
  const [theme, toggleTheme] = useTheme()
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

  return (
    <div className="flex min-h-screen" style={{ backgroundColor: 'var(--surface-page)' }}>
      <aside
        className="hidden md:flex flex-col shrink-0 transition-[width] duration-200"
        style={{
          width: collapsed ? '4.5rem' : '16rem',
          backgroundColor: 'var(--surface-nav)',
          borderRight: '1px solid var(--border-subtle)',
        }}
      >
        <div className={`flex items-center h-16 px-4 ${collapsed ? 'justify-center' : ''}`}>
          {collapsed ? <Logo variant="icon" size={30} /> : <Logo size={30} />}
        </div>

        <div className="flex-1 overflow-y-auto mc-scroll px-3 py-2">
          {!collapsed && (
            <div
              className="px-2 pb-2 text-[0.65rem] font-semibold uppercase tracking-[0.14em]"
              style={{ color: 'var(--text-faint)' }}
            >
              Workspace
            </div>
          )}
          <NavSection items={PRIMARY_NAV} collapsed={collapsed} />

          <div className="my-4 h-px" style={{ backgroundColor: 'var(--border-subtle)' }} />
          <NavSection items={SECONDARY_NAV} collapsed={collapsed} />
        </div>

        <div className="px-3 py-3" style={{ borderTop: '1px solid var(--border-subtle)' }}>
          {user && !collapsed && (
            <div className="px-2 pb-2">
              <div className="text-sm font-medium truncate" style={{ color: 'var(--text-strong)' }}>
                {user.name || user.email}
              </div>
              <div className="text-xs truncate" style={{ color: 'var(--text-faint)' }}>
                {user.email}
              </div>
            </div>
          )}
          <div className={`flex gap-1 ${collapsed ? 'flex-col items-center' : ''}`}>
            <button
              type="button"
              className="mc-btn mc-btn-ghost flex-1"
              onClick={toggleTheme}
              title={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
              aria-label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
            >
              {theme === 'dark' ? <SunIcon size={16} /> : <MoonIcon size={16} />}
              {!collapsed && <span>{theme === 'dark' ? 'Light' : 'Dark'}</span>}
            </button>
            <button
              type="button"
              className="mc-btn mc-btn-ghost"
              onClick={() => setCollapsed((c) => !c)}
              title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
              aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            >
              <SidebarIcon size={16} />
            </button>
          </div>
          {user && onSignOut && !collapsed && (
            <button
              type="button"
              className="mc-btn mc-btn-ghost w-full mt-1"
              onClick={onSignOut}
            >
              Sign out
            </button>
          )}
        </div>
      </aside>

      {/* Mobile navigation: the sidebar is replaced by a bottom bar */}
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
            className="mc-nav-item flex-col gap-0.5 px-3 text-[0.65rem]"
            aria-label={label}
          >
            <Icon size={19} />
            <span>{label}</span>
          </NavLink>
        ))}
      </nav>

      <main className="flex-1 min-w-0 pb-20 md:pb-0">{children}</main>
    </div>
  )
}

export function PageHeader({ title, description, actions }) {
  return (
    <header className="flex flex-wrap items-start justify-between gap-4 mb-6">
      <div className="min-w-0">
        <h1 className="text-2xl font-semibold">{title}</h1>
        {description && (
          <p className="mt-1 text-sm" style={{ color: 'var(--text-muted)' }}>
            {description}
          </p>
        )}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </header>
  )
}

export function Page({ children }) {
  return <div className="mx-auto w-full max-w-[1400px] px-5 py-6 md:px-8 md:py-8">{children}</div>
}
