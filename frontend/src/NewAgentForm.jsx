import { useState } from 'react'
import { createAgent } from './api'
import { RocketIcon } from './icons'

const defaults = {
  agent_name: '',
  provider: 'openai',
  model: 'gpt-4.1',
  voice: 'alloy',
  mode: 'realtime',
  temperature: 0.8,
  system_prompt: 'You are a helpful AI meeting assistant with access to persistent meeting memory tools. Keep responses concise and natural.',
  first_message: 'Hello! I am your persistent meeting companion. I remember past discussions, action items, and decisions.',
  activate: true,
}

export default function NewAgentForm({ onCreated, onClose }) {
  const [form, setForm] = useState(defaults)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  function update(field, value) {
    setForm((f) => ({ ...f, [field]: value }))
  }

  async function submit(e) {
    e.preventDefault()
    if (!form.agent_name.trim()) return
    setBusy(true)
    setError(null)
    try {
      const result = await createAgent({
        ...form,
        temperature: Number(form.temperature),
      })
      onCreated?.(result)
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="launch-panel new-agent-panel" onSubmit={submit}>
      <div className="launch-panel-head">
        <span>Set up a new agent</span>
        <button type="button" className="launch-close" onClick={onClose}>×</button>
      </div>

      <label className="field-label">
        Agent name <span className="field-required">Required</span>
      </label>
      <input
        type="text"
        placeholder="e.g. Sales Companion"
        value={form.agent_name}
        onChange={(e) => update('agent_name', e.target.value)}
        required
      />

      <div className="agent-form-grid">
        <label>
          Provider
          <input value={form.provider} onChange={(e) => update('provider', e.target.value)} placeholder="openai / xai / google" />
        </label>
        <label>
          Model
          <input value={form.model} onChange={(e) => update('model', e.target.value)} />
        </label>
        <label>
          Voice
          <input value={form.voice} onChange={(e) => update('voice', e.target.value)} />
        </label>
        <label>
          Mode
          <input value={form.mode} onChange={(e) => update('mode', e.target.value)} placeholder="realtime / pipeline" />
        </label>
      </div>

      <label className="field-label">System prompt</label>
      <textarea rows={3} value={form.system_prompt} onChange={(e) => update('system_prompt', e.target.value)} />

      <label className="field-label">First message</label>
      <textarea rows={2} value={form.first_message} onChange={(e) => update('first_message', e.target.value)} />

      <label className="checkbox-label" style={{ marginTop: 4 }}>
        <input
          type="checkbox"
          checked={form.activate}
          onChange={(e) => update('activate', e.target.checked)}
        />
        Make this the active agent (new bots will use it)
      </label>

      <button type="submit" disabled={busy || !form.agent_name.trim()}>
        <RocketIcon /> {busy ? 'Creating…' : 'Create agent'}
      </button>
      {error && <div className="launch-error">{error}</div>}
    </form>
  )
}
