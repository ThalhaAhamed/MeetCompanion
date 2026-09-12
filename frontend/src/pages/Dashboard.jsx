import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Page, PageHeader } from '../components/AppShell'
import { Badge, Card, EmptyState, ErrorMessage, Loading, StatTile } from '../components/ui'
import { MeetingsIcon, NotebookIcon, PlusIcon } from '../components/Icons'
import { listFolders, listMeetings, listNotes } from '../api'

function today() {
  return new Date().toISOString().slice(0, 10)
}

function formatTime(value) {
  if (!value) return ''
  return new Date(value).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
}

function statusTone(status) {
  if (['completed', 'done'].includes(status)) return 'success'
  if (['failed', 'error'].includes(status)) return 'danger'
  if (['recording', 'joining', 'in_progress'].includes(status)) return 'warning'
  return 'neutral'
}

export default function Dashboard() {
  const [meetings, setMeetings] = useState(null)
  const [notes, setNotes] = useState(null)
  const [counts, setCounts] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false

    Promise.all([
      listMeetings(today()).catch(() => []),
      listNotes({ limit: 5, sort: 'updated' }).catch(() => ({ notes: [], total: 0 })),
      listFolders().catch(() => ({ counts: {} })),
    ])
      .then(([meetingList, noteList, folderData]) => {
        if (cancelled) return
        setMeetings(Array.isArray(meetingList) ? meetingList : meetingList?.meetings || [])
        setNotes(noteList.notes || [])
        setCounts({ ...(folderData.counts || {}), notes: noteList.total || 0 })
      })
      .catch((err) => !cancelled && setError(err.message))

    return () => {
      cancelled = true
    }
  }, [])

  const live = useMemo(
    () => (meetings || []).filter((m) => !['completed', 'stopped', 'failed'].includes(m.status)),
    [meetings],
  )

  if (error) return <Page><ErrorMessage title="Could not load your workspace" detail={error} /></Page>
  if (meetings === null) return <Page><Loading /></Page>

  return (
    <Page>
      <PageHeader
        title="Dashboard"
        description="What is happening across your meetings and notes today."
        actions={
          <>
            <Link to="/notebook" className="mc-btn mc-btn-secondary">
              <PlusIcon size={16} /> New note
            </Link>
            <Link to="/meetings" className="mc-btn mc-btn-primary">
              <MeetingsIcon size={16} /> Meetings
            </Link>
          </>
        }
      />

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatTile label="Meetings today" value={meetings.length} tone="brand" />
        <StatTile label="Live now" value={live.length} tone="peach" />
        <StatTile label="Notes" value={counts?.notes ?? 0} tone="lavender" />
        <StatTile label="Favourites" value={counts?.favorites ?? 0} tone="rose" />
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        <Card padded={false}>
          <div
            className="flex items-center justify-between px-5 py-4"
            style={{ borderBottom: '1px solid var(--border-subtle)' }}
          >
            <h2 className="text-sm font-semibold">Today's meetings</h2>
            <Link to="/meetings" className="text-xs font-medium" style={{ color: 'var(--brand-soft-text)' }}>
              View all
            </Link>
          </div>

          {meetings.length === 0 ? (
            <EmptyState
              icon={<MeetingsIcon size={22} />}
              title="No meetings today"
              description="Launch a bot into a call and it will show up here."
              action={
                <Link to="/meetings" className="mc-btn mc-btn-secondary">
                  Go to meetings
                </Link>
              }
            />
          ) : (
            <ul className="divide-y" style={{ borderColor: 'var(--border-subtle)' }}>
              {meetings.slice(0, 6).map((meeting) => (
                <li key={meeting.id}>
                  <Link
                    to={`/meetings/${meeting.id}`}
                    className="flex items-center justify-between gap-3 px-5 py-3 transition-colors hover:bg-[var(--surface-raised)]"
                  >
                    <div className="min-w-0">
                      <div className="truncate text-sm font-medium" style={{ color: 'var(--text-strong)' }}>
                        {meeting.title || 'Untitled meeting'}
                      </div>
                      <div className="mt-0.5 text-xs" style={{ color: 'var(--text-faint)' }}>
                        {formatTime(meeting.started_at || meeting.created_at)}
                        {meeting.created_by_name ? ` · ${meeting.created_by_name}` : ''}
                      </div>
                    </div>
                    <Badge tone={statusTone(meeting.status)}>{meeting.status}</Badge>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card padded={false}>
          <div
            className="flex items-center justify-between px-5 py-4"
            style={{ borderBottom: '1px solid var(--border-subtle)' }}
          >
            <h2 className="text-sm font-semibold">Recent notes</h2>
            <Link to="/notebook" className="text-xs font-medium" style={{ color: 'var(--brand-soft-text)' }}>
              Open notebook
            </Link>
          </div>

          {(notes || []).length === 0 ? (
            <EmptyState
              icon={<NotebookIcon size={22} />}
              title="Your notebook is empty"
              description="Capture a thought, or let a meeting write one for you."
              action={
                <Link to="/notebook" className="mc-btn mc-btn-secondary">
                  Create a note
                </Link>
              }
            />
          ) : (
            <ul className="divide-y" style={{ borderColor: 'var(--border-subtle)' }}>
              {notes.map((note) => (
                <li key={note.id}>
                  <Link
                    to={`/notebook/${note.id}`}
                    className="block px-5 py-3 transition-colors hover:bg-[var(--surface-raised)]"
                  >
                    <div className="truncate text-sm font-medium" style={{ color: 'var(--text-strong)' }}>
                      {note.title}
                    </div>
                    {note.excerpt && (
                      <div className="mt-0.5 line-clamp-1 text-xs" style={{ color: 'var(--text-muted)' }}>
                        {note.excerpt}
                      </div>
                    )}
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </Page>
  )
}
