import { useState } from 'react'
import { createMeeting } from './api'

export default function LaunchBot({ onLaunched }) {
  const [open, setOpen] = useState(false)
  const [url, setUrl] = useState('')
  const [title, setTitle] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [success, setSuccess] = useState(null)

  async function submit(e) {
    e.preventDefault()
    if (!url.trim()) return
    setBusy(true)
    setError(null)
    setSuccess(null)
    try {
      const meeting = await createMeeting({ meeting_url: url.trim(), title: title.trim() })
      setSuccess(meeting)
      setUrl('')
      setTitle('')
      onLaunched?.(meeting)
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  if (!open) {
    return (
      <button className="launch-btn" onClick={() => setOpen(true)}>
        + Launch bot
      </button>
    )
  }

  return (
    <form className="launch-panel" onSubmit={submit}>
      <div className="launch-panel-head">
        <span>Launch a bot into a meeting</span>
        <button type="button" className="launch-close" onClick={() => setOpen(false)}>×</button>
      </div>
      <label className="field-label">
        Meeting link <span className="field-required">Required</span>
      </label>
      <input
        type="url"
        placeholder="https://meet.google.com/xxx-xxxx-xxx"
        value={url}
        onChange={(e) => setUrl(e.target.value)}
        required
      />
      <label className="field-label">Title</label>
      <input
        type="text"
        placeholder="Optional"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
      />
      <button type="submit" disabled={busy || !url.trim()}>
        {busy ? 'Deploying…' : 'Deploy bot'}
      </button>
      {error && <div className="launch-error">{error}</div>}
      {success && (
        <div className="launch-success">
          Bot deployed — status: {success.status}
        </div>
      )}
    </form>
  )
}
