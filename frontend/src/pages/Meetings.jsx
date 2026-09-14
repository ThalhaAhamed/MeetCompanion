import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { Page, PageHeader } from '../components/AppShell'
import { MeetingsIcon, PlusIcon, SearchIcon } from '../components/Icons'
import { Badge, Card, EmptyState, ErrorMessage, ExportMenu, Field, Loading, Modal, Spinner } from '../components/ui'
import {
  createMeeting,
  deleteMeeting,
  exportMeetingUrl,
  getMeeting,
  getTranscript,
  importBot,
  listImportableBots,
  listMeetings,
  reprocessMeeting,
  stopMeetingBot,
  uploadTranscript,
} from '../api'

const LIVE_STATUSES = ['pending', 'joining', 'recording', 'in_progress']
// Stop bot only makes sense once there is a bot to stop.
const STOPPABLE_STATUSES = ['joining', 'recording', 'in_progress']

/**
 * Some summaries were stored with escaped newlines rather than real ones, so
 * a literal "\n" reaches the browser and renders as text. Convert those back
 * before display; genuine newlines are unaffected.
 */
function withRealNewlines(text) {
  return (text || '').replace(/\\r\\n|\\n/g, '\n')
}

function statusTone(status) {
  if (['completed', 'done'].includes(status)) return 'success'
  if (['failed', 'error'].includes(status)) return 'danger'
  if (LIVE_STATUSES.includes(status)) return 'warning'
  return 'neutral'
}

function LaunchBotModal({ open, onClose, onLaunched }) {
  const [url, setUrl] = useState('')
  const [title, setTitle] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  async function submit(event) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const meeting = await createMeeting({ meeting_url: url.trim(), title: title.trim() || undefined })
      // The API returns 201 even when the bot failed to deploy, with the
      // reason on the meeting - surfacing it as success would be a lie.
      if (meeting.processing_error) {
        setError(meeting.processing_error)
        return
      }
      setUrl('')
      setTitle('')
      onLaunched?.(meeting)
      onClose()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="Launch a bot into a meeting">
      <form onSubmit={submit}>
        <Field label="Meeting link" htmlFor="meeting-url">
          <input
            id="meeting-url"
            className="mc-input"
            required
            type="url"
            placeholder="https://meet.google.com/xxx-xxxx-xxx"
            value={url}
            onChange={(event) => setUrl(event.target.value)}
          />
        </Field>
        <Field label="Title" hint="Optional label for this dashboard." htmlFor="meeting-title">
          <input
            id="meeting-title"
            className="mc-input"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
          />
        </Field>

        {error && <div className="mb-4"><ErrorMessage title="Could not deploy the bot" detail={error} /></div>}

        <button type="submit" className="mc-btn mc-btn-primary w-full" disabled={busy || !url.trim()}>
          {busy ? <Spinner size={14} /> : null} Deploy bot
        </button>
      </form>
    </Modal>
  )
}

function ImportBotsModal({ open, onClose, onImported }) {
  const [candidates, setCandidates] = useState(null)
  const [error, setError] = useState(null)
  const [importingId, setImportingId] = useState(null)
  const [search, setSearch] = useState('')

  useEffect(() => {
    if (!open) return
    setCandidates(null)
    listImportableBots()
      .then((data) => setCandidates(data.importable || []))
      .catch((err) => setError(err.message))
  }, [open])

  const filtered = (candidates || []).filter((bot) => {
    if (!search.trim()) return true
    const haystack = `${bot.bot_username || ''} ${bot.meeting_url || ''}`.toLowerCase()
    return haystack.includes(search.trim().toLowerCase())
  })

  async function handleImport(bot) {
    setImportingId(bot.bot_id)
    try {
      const meeting = await importBot({
        bot_id: bot.bot_id,
        platform: bot.platform,
        meeting_url: bot.meeting_url,
        title: bot.bot_username ? `${bot.bot_username} (imported)` : undefined,
      })
      onImported?.(meeting)
      setCandidates((current) => current.filter((c) => c.bot_id !== bot.bot_id))
    } catch (err) {
      setError(err.message)
    } finally {
      setImportingId(null)
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="Import past bots" width="36rem">
      <p className="mb-4 text-sm" style={{ color: 'var(--text-muted)' }}>
        Bots run on your MeetStream account outside Meet Companion. Importing pulls the transcript
        and runs it through the same memory extraction as any other meeting.
      </p>

      {error && <div className="mb-4"><ErrorMessage title="Import failed" detail={error} /></div>}

      {candidates === null ? (
        <Loading />
      ) : candidates.length === 0 ? (
        <EmptyState title="Nothing to import" description="Every bot on this account is already tracked here." />
      ) : (
        <>
          <div className="relative mb-3">
            <span className="absolute left-2.5 top-2.5" style={{ color: 'var(--text-faint)' }}>
              <SearchIcon size={15} />
            </span>
            <input
              className="mc-input pl-8"
              placeholder="Search bots…"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </div>

          <ul className="mc-scroll max-h-80 divide-y overflow-y-auto" style={{ borderColor: 'var(--border-subtle)' }}>
            {filtered.map((bot) => (
              <li key={bot.bot_id} className="flex items-center justify-between gap-3 py-3">
                <div className="min-w-0">
                  <div className="truncate text-sm font-medium">{bot.bot_username || 'Untitled bot'}</div>
                  <div className="mt-0.5 flex flex-wrap items-center gap-1.5">
                    {bot.platform && <Badge>{bot.platform}</Badge>}
                    {bot.status && <Badge tone={statusTone(bot.status)}>{bot.status}</Badge>}
                    {bot.start_time && (
                      <span className="text-xs" style={{ color: 'var(--text-faint)' }}>
                        {new Date(bot.start_time).toLocaleString()}
                      </span>
                    )}
                  </div>
                </div>
                <button
                  type="button"
                  className="mc-btn mc-btn-secondary"
                  onClick={() => handleImport(bot)}
                  disabled={importingId === bot.bot_id}
                >
                  {importingId === bot.bot_id ? <Spinner size={13} /> : null} Import
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
    </Modal>
  )
}

function UploadTranscriptModal({ open, onClose, onUploaded }) {
  const [form, setForm] = useState({ title: '', transcript: '', project_name: '', started_at: '' })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  function update(key, value) {
    setForm((current) => ({ ...current, [key]: value }))
  }

  async function submit(event) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const meeting = await uploadTranscript({
        title: form.title,
        transcript: form.transcript,
        project_name: form.project_name || null,
        started_at: form.started_at ? new Date(form.started_at).toISOString() : null,
      })
      onUploaded?.(meeting)
      setForm({ title: '', transcript: '', project_name: '', started_at: '' })
      onClose()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="Upload a transcript" width="38rem">
      <p className="mb-4 text-sm" style={{ color: 'var(--text-muted)' }}>
        Paste a transcript from anywhere - another recorder, meeting notes, a call you transcribed
        yourself. One line per utterance, <code>Name: what they said</code>. It goes through the same
        extraction as a recorded call.
      </p>
      <form onSubmit={submit}>
        <Field label="Title" htmlFor="up-title">
          <input id="up-title" className="mc-input" required value={form.title} onChange={(e) => update('title', e.target.value)} />
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="When" htmlFor="up-when" hint="Used to resolve deadlines like “by Friday”.">
            <input id="up-when" type="datetime-local" className="mc-input" value={form.started_at} onChange={(e) => update('started_at', e.target.value)} />
          </Field>
          <Field label="Project" htmlFor="up-project">
            <input id="up-project" className="mc-input" value={form.project_name} onChange={(e) => update('project_name', e.target.value)} />
          </Field>
        </div>
        <Field label="Transcript" htmlFor="up-text">
          <textarea
            id="up-text"
            className="mc-input min-h-56 font-mono text-xs"
            required
            placeholder={'Priya: Morning everyone. Quick agenda…\nMarcus: Let\'s start with Northwind…'}
            value={form.transcript}
            onChange={(e) => update('transcript', e.target.value)}
          />
        </Field>
        {error && <div className="mb-4"><ErrorMessage title="Upload failed" detail={error} /></div>}
        <button type="submit" className="mc-btn mc-btn-primary w-full" disabled={busy || !form.transcript.trim()}>
          {busy ? <Spinner size={14} /> : null} {busy ? 'Uploading…' : 'Upload and extract'}
        </button>
      </form>
    </Modal>
  )
}

function MeetingDetail({ meetingId, onChanged, onDeleted }) {
  const [meeting, setMeeting] = useState(null)
  const [transcript, setTranscript] = useState(null)
  const [tab, setTab] = useState('summary')
  const [error, setError] = useState(null)
  const [stopping, setStopping] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [reprocessing, setReprocessing] = useState(false)

  useEffect(() => {
    setMeeting(null)
    setTab('summary')
    getMeeting(meetingId).then(setMeeting).catch((err) => setError(err.message))
  }, [meetingId])

  // Extraction runs in the background after upload/reprocess; keep the
  // page current until it settles, then tell the list to refresh too.
  const inFlight = meeting && ['queued_for_processing', 'processing'].includes(meeting.processing_status)
  useEffect(() => {
    if (!inFlight) return undefined
    const timer = setInterval(async () => {
      try {
        const fresh = await getMeeting(meetingId)
        setMeeting(fresh)
        if (!['queued_for_processing', 'processing'].includes(fresh.processing_status)) {
          setTranscript(null)
          onChanged?.()
        }
      } catch {
        // Transient; the next tick retries.
      }
    }, 2500)
    return () => clearInterval(timer)
  }, [inFlight, meetingId, onChanged])

  useEffect(() => {
    if (tab !== 'transcript' || transcript !== null) return
    getTranscript(meetingId).then(setTranscript).catch(() => setTranscript([]))
  }, [tab, meetingId, transcript])

  async function remove() {
    if (!window.confirm('Delete this meeting, its transcript, memories, action items and note? This cannot be undone.')) return
    setDeleting(true)
    setError(null)
    try {
      await deleteMeeting(meetingId)
      onDeleted?.() // leave the (now gone) detail route before the list refreshes
      onChanged?.()
    } catch (err) {
      setError(err.message)
    } finally {
      setDeleting(false)
    }
  }

  async function stop() {
    setStopping(true)
    try {
      await stopMeetingBot(meetingId)
      setMeeting(await getMeeting(meetingId))
      onChanged?.()
    } catch (err) {
      setError(err.message)
    } finally {
      setStopping(false)
    }
  }

  async function reprocess() {
    setReprocessing(true)
    setError(null)
    try {
      setMeeting(await reprocessMeeting(meetingId))
    } catch (err) {
      setError(err.message)
    } finally {
      setReprocessing(false)
    }
  }

  if (error) return <ErrorMessage title="Could not load meeting" detail={error} />
  if (!meeting) return <Loading />

  const memories = meeting.memories || []
  const actionItems = meeting.action_items || []
  const isLive = STOPPABLE_STATUSES.includes(meeting.status) && Boolean(meeting.meetstream_bot_id)

  const tabs = [
    { id: 'summary', label: 'Summary' },
    { id: 'memories', label: `Memories (${memories.length})` },
    { id: 'actions', label: `Action items (${actionItems.length})` },
    { id: 'transcript', label: 'Transcript' },
  ]

  return (
    <Card padded={false}>
      <div className="px-5 py-4" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="truncate text-lg font-semibold">{meeting.title || 'Untitled meeting'}</h2>
            <div className="mt-1.5 flex flex-wrap items-center gap-2 text-xs" style={{ color: 'var(--text-muted)' }}>
              <Badge tone={statusTone(meeting.status)}>{meeting.status}</Badge>
              {meeting.platform && <Badge>{meeting.platform}</Badge>}
              {meeting.created_by_name && <span>Started by {meeting.created_by_name}</span>}
            </div>
          </div>
          <div className="flex items-center gap-2">
            {!isLive && (
              <button
                type="button"
                className="mc-btn mc-btn-secondary"
                onClick={reprocess}
                disabled={reprocessing || inFlight}
                title="Run extraction again with the current AI provider"
              >
                {reprocessing || inFlight ? <Spinner size={13} /> : null} {inFlight ? 'Extracting…' : 'Reprocess'}
              </button>
            )}
            {isLive && (
              <button type="button" className="mc-btn mc-btn-danger" onClick={stop} disabled={stopping}>
                {stopping ? <Spinner size={13} /> : null} Stop bot
              </button>
            )}
            <ExportMenu
              label="Export"
              options={[
                { href: exportMeetingUrl(meetingId, 'md'), label: 'Markdown (.md)' },
                { href: exportMeetingUrl(meetingId, 'json'), label: 'JSON (.json)' },
              ]}
            />
            {!isLive && (
              <button
                type="button"
                className="mc-btn mc-btn-secondary"
                onClick={remove}
                disabled={deleting}
                title="Delete this meeting and everything extracted from it"
              >
                {deleting ? <Spinner size={13} /> : null} Delete
              </button>
            )}
          </div>
        </div>

        {meeting.processing_error && (
          <div className="mt-3">
            <ErrorMessage title="Processing problem" detail={meeting.processing_error} />
          </div>
        )}
      </div>

      <div className="flex gap-1 overflow-x-auto px-3 py-2" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
        {tabs.map((item) => (
          <button
            key={item.id}
            type="button"
            className="mc-nav-item whitespace-nowrap"
            aria-current={tab === item.id ? 'page' : undefined}
            onClick={() => setTab(item.id)}
          >
            {item.label}
          </button>
        ))}
      </div>

      <div className="mc-scroll max-h-[60vh] overflow-y-auto p-5">
        {tab === 'summary' &&
          (meeting.summary ? (
            <p className="whitespace-pre-wrap text-sm leading-relaxed">{withRealNewlines(meeting.summary)}</p>
          ) : (
            <EmptyState title="No summary yet" description="A summary appears once the transcript has been processed." />
          ))}

        {tab === 'memories' &&
          (memories.length === 0 ? (
            <EmptyState title="No memories extracted" />
          ) : (
            <ul className="flex flex-col gap-3">
              {memories.map((memory) => (
                <li key={memory.id} className="mc-panel p-3">
                  <Badge tone="brand">{memory.type}</Badge>
                  <p className="mt-2 text-sm">{memory.content}</p>
                  {memory.speaker && (
                    <p className="mt-1 text-xs" style={{ color: 'var(--text-faint)' }}>— {memory.speaker}</p>
                  )}
                </li>
              ))}
            </ul>
          ))}

        {tab === 'actions' &&
          (actionItems.length === 0 ? (
            <EmptyState title="No action items" />
          ) : (
            <ul className="flex flex-col gap-2">
              {actionItems.map((item) => (
                <li key={item.id} className="mc-panel flex items-start justify-between gap-3 p-3">
                  <div className="min-w-0">
                    <p className="text-sm">{item.task}</p>
                    <div className="mt-1 flex flex-wrap gap-1.5">
                      {item.owner && <Badge>{item.owner}</Badge>}
                      {item.due_date && <Badge tone="warning">due {item.due_date}</Badge>}
                    </div>
                  </div>
                  <Badge tone={item.status === 'completed' ? 'success' : 'neutral'}>{item.status}</Badge>
                </li>
              ))}
            </ul>
          ))}

        {tab === 'transcript' &&
          (transcript === null ? (
            <Loading />
          ) : transcript.length === 0 ? (
            <EmptyState title="No transcript available" />
          ) : (
            <ul className="flex flex-col gap-2.5">
              {transcript.map((segment, index) => (
                <li key={segment.id || index} className="text-sm">
                  <span className="font-medium" style={{ color: 'var(--text-strong)' }}>
                    {segment.speaker || 'Unknown'}:
                  </span>{' '}
                  <span style={{ color: 'var(--text-default)' }}>{segment.text}</span>
                </li>
              ))}
            </ul>
          ))}
      </div>
    </Card>
  )
}

export default function Meetings() {
  const { meetingId } = useParams()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()

  const [day, setDay] = useState(() => new Date().toISOString().slice(0, 10))
  const [meetings, setMeetings] = useState(null)
  const [error, setError] = useState(null)
  // Seeded from ?q= so the header search reaches this page too.
  const [filter, setFilter] = useState(() => searchParams.get('q') || '')
  const [launchOpen, setLaunchOpen] = useState(false)
  const [importOpen, setImportOpen] = useState(false)
  const [uploadOpen, setUploadOpen] = useState(false)

  const refresh = useCallback(async () => {
    try {
      const data = await listMeetings(day)
      setMeetings(Array.isArray(data) ? data : data?.meetings || [])
    } catch (err) {
      setError(err.message)
    }
  }, [day])

  useEffect(() => {
    setMeetings(null)
    refresh()
  }, [refresh])

  // Opening on today is right for someone using this daily, but it strands
  // anyone returning after a gap on an empty page while meetings sit a few
  // days back. If today is empty, fall through to the most recent day that
  // has something - once only, so it never fights a date the user picked.
  // A ref, not state: flipping state here would re-run this effect, and its
  // cleanup would cancel the request that is still in flight.
  const jumpedToRecent = useRef(false)
  useEffect(() => {
    if (jumpedToRecent.current || meetings === null || meetings.length > 0) return
    jumpedToRecent.current = true

    listMeetings(null)
      .then((data) => {
        const all = Array.isArray(data) ? data : data?.meetings || []
        const latest = all
          .map((meeting) => (meeting.started_at || meeting.created_at || '').slice(0, 10))
          .filter(Boolean)
          .sort()
          .pop()
        if (latest && latest !== day) setDay(latest)
      })
      .catch(() => {})
  }, [meetings, day])

  const urlQuery = searchParams.get('q') || ''
  useEffect(() => {
    setFilter((current) => (current === urlQuery ? current : urlQuery))
  }, [urlQuery])

  function handleLaunched(meeting) {
    const meetingDay = (meeting.started_at || meeting.created_at || '').slice(0, 10)
    if (meetingDay && meetingDay !== day) setDay(meetingDay)
    else refresh()
    navigate(`/meetings/${meeting.id}`)
  }

  const visible = (meetings || []).filter((meeting) => {
    if (!filter.trim()) return true
    return (meeting.title || '').toLowerCase().includes(filter.trim().toLowerCase())
  })

  return (
    <Page>
      <PageHeader
        title="Meetings"
        description="Calls captured by Meet Companion, with everything extracted from them."
        actions={
          <>
            <input
              type="date"
              className="mc-input w-auto"
              value={day}
              onChange={(event) => setDay(event.target.value)}
              aria-label="Day"
            />
            <button type="button" className="mc-btn mc-btn-secondary" onClick={() => setUploadOpen(true)}>
              Upload transcript
            </button>
            <button type="button" className="mc-btn mc-btn-secondary" onClick={() => setImportOpen(true)}>
              Import past bots
            </button>
            <button type="button" className="mc-btn mc-btn-primary" onClick={() => setLaunchOpen(true)}>
              <PlusIcon size={16} /> Launch bot
            </button>
          </>
        }
      />

      {error && <div className="mb-4"><ErrorMessage title="Could not load meetings" detail={error} /></div>}

      <div className="grid gap-5 lg:grid-cols-[22rem_1fr]">
        <Card padded={false} className="self-start">
          <div className="p-3" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
            <input
              className="mc-input"
              placeholder="Filter by title…"
              value={filter}
              onChange={(event) => setFilter(event.target.value)}
              aria-label="Filter meetings"
            />
          </div>

          {meetings === null ? (
            <Loading />
          ) : visible.length === 0 ? (
            <EmptyState
              icon={<MeetingsIcon size={22} />}
              title="No meetings on this day"
              description="Launch a bot into a call to see it here."
            />
          ) : (
            <ul className="mc-scroll max-h-[65vh] divide-y overflow-y-auto" style={{ borderColor: 'var(--border-subtle)' }}>
              {visible.map((meeting) => (
                <li key={meeting.id}>
                  <button
                    type="button"
                    className="w-full px-4 py-3 text-left transition-colors hover:bg-[var(--surface-raised)]"
                    style={{ backgroundColor: meeting.id === meetingId ? 'var(--brand-soft)' : undefined }}
                    aria-label={`Open meeting: ${meeting.title || 'Untitled meeting'}`}
                    aria-current={meeting.id === meetingId ? 'true' : undefined}
                    onClick={() => navigate(`/meetings/${meeting.id}`)}
                  >
                    <div className="truncate text-sm font-medium" style={{ color: 'var(--text-strong)' }}>
                      {meeting.title || 'Untitled meeting'}
                    </div>
                    <div className="mt-1 flex flex-wrap items-center gap-1.5">
                      <Badge tone={statusTone(meeting.status)}>{meeting.status}</Badge>
                      {meeting.created_by_name && (
                        <span className="text-xs" style={{ color: 'var(--text-faint)' }}>
                          {meeting.created_by_name}
                        </span>
                      )}
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <div className="min-w-0">
          {meetingId ? (
            <MeetingDetail meetingId={meetingId} onChanged={refresh} onDeleted={() => navigate('/meetings')} />
          ) : (
            <Card>
              <EmptyState
                icon={<MeetingsIcon size={22} />}
                title="Select a meeting"
                description="Its summary, decisions, action items and transcript appear here."
              />
            </Card>
          )}
        </div>
      </div>

      <LaunchBotModal open={launchOpen} onClose={() => setLaunchOpen(false)} onLaunched={handleLaunched} />
      <ImportBotsModal open={importOpen} onClose={() => setImportOpen(false)} onImported={handleLaunched} />
      <UploadTranscriptModal open={uploadOpen} onClose={() => setUploadOpen(false)} onUploaded={handleLaunched} />
    </Page>
  )
}
