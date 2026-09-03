import { useEffect, useState } from 'react'
import { getAgent, updateAgent, listAgents, activateAgent } from './api'
import NewAgentForm from './NewAgentForm'
import EmptyState from './EmptyState'
import { RocketIcon, InboxIcon } from './icons'

const emptyForm = {
  system_prompt: '',
  first_message: '',
  voice: '',
  provider: '',
  model: '',
  temperature: '',
  response_modality: '',
  tool_results_to_chat: false,
}

export default function AgentSettings() {
  const [raw, setRaw] = useState(null)
  const [form, setForm] = useState(emptyForm)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState(null)
  const [saved, setSaved] = useState(false)

  const [agents, setAgents] = useState([])
  const [agentsLoading, setAgentsLoading] = useState(true)
  const [agentsError, setAgentsError] = useState(null)
  const [activatingId, setActivatingId] = useState(null)
  const [showNewForm, setShowNewForm] = useState(false)

  function load() {
    setLoading(true)
    setError(null)
    getAgent()
      .then((data) => {
        setRaw(data)
        const cfg = data.agent_config || data
        const model = cfg.Model || {}
        const agent = cfg.Agent || {}
        setForm({
          system_prompt: model.system_prompt || '',
          first_message: model.first_message || '',
          voice: model.voice || '',
          provider: model.provider || '',
          model: model.model || '',
          temperature: model.temperature ?? '',
          response_modality: agent.response_modality || '',
          tool_results_to_chat: !!agent.tool_results_to_chat,
        })
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }

  function loadAgents() {
    setAgentsLoading(true)
    setAgentsError(null)
    listAgents()
      .then((data) => setAgents(data.agent_configs || []))
      .catch((e) => setAgentsError(e.message))
      .finally(() => setAgentsLoading(false))
  }

  useEffect(load, [])
  useEffect(loadAgents, [])

  function update(field, value) {
    setForm((f) => ({ ...f, [field]: value }))
    setSaved(false)
  }

  async function save(e) {
    e.preventDefault()
    setSaving(true)
    setSaveError(null)
    setSaved(false)
    try {
      await updateAgent({
        system_prompt: form.system_prompt,
        first_message: form.first_message,
        voice: form.voice || undefined,
        provider: form.provider || undefined,
        model: form.model || undefined,
        temperature: form.temperature === '' ? undefined : Number(form.temperature),
        response_modality: form.response_modality || undefined,
        tool_results_to_chat: form.tool_results_to_chat,
      })
      setSaved(true)
      load()
    } catch (e) {
      setSaveError(e.message)
    } finally {
      setSaving(false)
    }
  }

  async function handleActivate(agentConfigId) {
    setActivatingId(agentConfigId)
    try {
      await activateAgent(agentConfigId)
      loadAgents()
      load()
    } catch (e) {
      setAgentsError(e.message)
    } finally {
      setActivatingId(null)
    }
  }

  function handleCreated() {
    setShowNewForm(false)
    loadAgents()
    load()
  }

  const cfg = raw?.agent_config || raw
  const agentName = cfg?.AgentName
  const agentConfigId = cfg?.AgentConfigID
  const mode = cfg?.Mode

  return (
    <div className="app">
      <header className="topbar">
        <div>
          <h1>Agent settings</h1>
          <p className="subtitle">Configure the MIA agent MeetStream deploys into your meetings.</p>
        </div>
        <div className="topbar-actions">
          <button className="launch-btn" onClick={() => setShowNewForm((v) => !v)}>
            <RocketIcon /> New agent
          </button>
          {showNewForm && <NewAgentForm onCreated={handleCreated} onClose={() => setShowNewForm(false)} />}
        </div>
      </header>

      <div className="layout">
        <div className="column">
          <section>
            <div className="section-head">
              <h2>Your agents ({agents.length})</h2>
            </div>
            {agentsError && <div className="error">Failed to load agents: {agentsError}</div>}
            {agentsLoading && <div className="loading">Loading…</div>}
            {!agentsLoading && agents.length === 0 && (
              <EmptyState icon={<InboxIcon />} title="No agents yet" subtitle="Create one to get started." />
            )}
            <ul className="list">
              {agents.map((a) => (
                <li key={a.AgentConfigID} className={`list-item doc-item ${a.IsActive ? 'selected' : ''}`}>
                  <div className="list-item-title">{a.AgentName || 'Untitled agent'}</div>
                  <div className="list-item-meta">
                    {a.IsActive ? (
                      <span className="badge status-completed">Active</span>
                    ) : (
                      <button
                        className="upload-btn"
                        onClick={() => handleActivate(a.AgentConfigID)}
                        disabled={activatingId === a.AgentConfigID}
                      >
                        {activatingId === a.AgentConfigID ? 'Activating…' : 'Set active'}
                      </button>
                    )}
                    {a.Mode && <span className="tag">{a.Mode}</span>}
                    {a.Model?.provider && <span className="tag">{a.Model.provider}</span>}
                  </div>
                </li>
              ))}
            </ul>
          </section>
        </div>

        <div className="column detail-column agent-panel">
          {loading && <div className="loading">Loading agent config…</div>}
          {error && <div className="error">Failed to load agent: {error}</div>}

          {!loading && !error && (
            <>
              <div className="detail-meta">
                {agentName && <span className="tag">{agentName}</span>}
                {mode && <span className="tag">{mode}</span>}
                {agentConfigId && <span className="tag">{agentConfigId}</span>}
              </div>

              <form className="agent-form" onSubmit={save}>
                <label>
                  System prompt
                  <textarea
                    rows={4}
                    value={form.system_prompt}
                    onChange={(e) => update('system_prompt', e.target.value)}
                  />
                </label>

                <label>
                  First message
                  <textarea
                    rows={2}
                    value={form.first_message}
                    onChange={(e) => update('first_message', e.target.value)}
                  />
                </label>

                <div className="agent-form-grid">
                  <label>
                    Provider
                    <input value={form.provider} onChange={(e) => update('provider', e.target.value)} placeholder="openai / xai / anthropic" />
                  </label>
                  <label>
                    Model
                    <input value={form.model} onChange={(e) => update('model', e.target.value)} placeholder="not set on this agent" />
                  </label>
                  <label>
                    Voice
                    <input value={form.voice} onChange={(e) => update('voice', e.target.value)} />
                  </label>
                  <label>
                    Temperature
                    <input type="number" step="0.1" min="0" max="2" value={form.temperature} onChange={(e) => update('temperature', e.target.value)} />
                  </label>
                  <label>
                    Response modality
                    <input value={form.response_modality} onChange={(e) => update('response_modality', e.target.value)} placeholder="text / audio" />
                  </label>
                  <label className="checkbox-label">
                    <input
                      type="checkbox"
                      checked={form.tool_results_to_chat}
                      onChange={(e) => update('tool_results_to_chat', e.target.checked)}
                    />
                    Post tool results to chat
                  </label>
                </div>

                <div className="agent-form-actions">
                  <button type="submit" disabled={saving}>{saving ? 'Saving…' : 'Save changes'}</button>
                  {saved && <span className="launch-success">Saved.</span>}
                  {saveError && <span className="launch-error">{saveError}</span>}
                </div>
              </form>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
