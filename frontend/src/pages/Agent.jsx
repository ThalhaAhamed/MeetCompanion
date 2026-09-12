import { useCallback, useEffect, useState } from 'react'
import { Page, PageHeader } from '../components/AppShell'
import { AskAiIcon, CheckIcon, PlusIcon } from '../components/Icons'
import {
  Badge,
  Card,
  EmptyState,
  ErrorMessage,
  Field,
  Loading,
  Modal,
  SectionCard,
  Spinner,
} from '../components/ui'
import {
  activateAgent,
  createAgent,
  getAgent,
  getAgentCredentials,
  listAgents,
  listImportableAgents,
  updateAgent,
} from '../api'

const MODES = ['realtime', 'pipeline']
const MODALITIES = ['text', 'audio', 'chat']

const EMPTY_FORM = {
  system_prompt: '',
  first_message: '',
  provider: '',
  model: '',
  voice: '',
  temperature: '',
  response_modality: '',
  tool_results_to_chat: false,
}

function NewAgentModal({ open, onClose, onCreated }) {
  const [form, setForm] = useState({
    agent_name: '',
    system_prompt: '',
    use_default_prompt: true,
    provider: 'openai',
    model: 'gpt-4.1-mini',
    voice: 'alloy',
    mode: 'realtime',
    activate: true,
  })
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
      await createAgent(form)
      onCreated?.()
      onClose()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="New agent" width="34rem">
      <form onSubmit={submit}>
        <Field label="Agent name" hint="Participants address the agent by this name." htmlFor="agent-name">
          <input
            id="agent-name"
            className="mc-input"
            required
            value={form.agent_name}
            onChange={(event) => update('agent_name', event.target.value)}
          />
        </Field>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Provider" htmlFor="agent-provider">
            <input
              id="agent-provider"
              className="mc-input"
              value={form.provider}
              onChange={(event) => update('provider', event.target.value)}
            />
          </Field>
          <Field label="Model" htmlFor="agent-model">
            <input
              id="agent-model"
              className="mc-input"
              value={form.model}
              onChange={(event) => update('model', event.target.value)}
            />
          </Field>
          <Field label="Voice" htmlFor="agent-voice">
            <input
              id="agent-voice"
              className="mc-input"
              value={form.voice}
              onChange={(event) => update('voice', event.target.value)}
            />
          </Field>
          <Field label="Mode" htmlFor="agent-mode">
            <select
              id="agent-mode"
              className="mc-input"
              value={form.mode}
              onChange={(event) => update('mode', event.target.value)}
            >
              {MODES.map((mode) => (
                <option key={mode} value={mode}>{mode}</option>
              ))}
            </select>
          </Field>
        </div>

        <Field
          label="Extra instructions"
          hint={
            form.use_default_prompt
              ? 'Layered on top of the built-in policy: name-gated activation, date reasoning, no invented answers.'
              : 'Used verbatim as the entire system prompt. None of the built-in behaviour is guaranteed.'
          }
          htmlFor="agent-prompt"
        >
          <textarea
            id="agent-prompt"
            className="mc-input min-h-24"
            value={form.system_prompt}
            onChange={(event) => update('system_prompt', event.target.value)}
          />
        </Field>

        <label className="mb-4 flex items-center gap-2 text-sm" style={{ color: 'var(--text-muted)' }}>
          <input
            type="checkbox"
            checked={form.use_default_prompt}
            onChange={(event) => update('use_default_prompt', event.target.checked)}
          />
          Keep the built-in activation policy
        </label>

        {error && <div className="mb-4"><ErrorMessage title="Could not create the agent" detail={error} /></div>}

        <button type="submit" className="mc-btn mc-btn-primary w-full" disabled={busy || !form.agent_name.trim()}>
          {busy ? <Spinner size={14} /> : null} Create agent
        </button>
      </form>
    </Modal>
  )
}

function ImportAgentsModal({ open, onClose, onImported }) {
  const [candidates, setCandidates] = useState(null)
  const [error, setError] = useState(null)
  const [busyId, setBusyId] = useState(null)

  useEffect(() => {
    if (!open) return
    setCandidates(null)
    setError(null)
    listImportableAgents()
      .then((data) => setCandidates(data.importable || []))
      .catch((err) => setError(err.message))
  }, [open])

  async function claim(agent) {
    setBusyId(agent.AgentConfigID)
    try {
      await activateAgent(agent.AgentConfigID)
      onImported?.()
      onClose()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusyId(null)
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="Import an agent from MeetStream" width="34rem">
      <p className="mb-4 text-sm" style={{ color: 'var(--text-muted)' }}>
        Agents that exist on your MeetStream account but that nobody here has claimed — created on
        MeetStream's own dashboard, or left behind by a removed member.
      </p>

      {error && <div className="mb-4"><ErrorMessage title="Import failed" detail={error} /></div>}

      {candidates === null && !error ? (
        <Loading />
      ) : candidates?.length === 0 ? (
        <EmptyState title="Nothing to import" description="Every agent on this account is already claimed." />
      ) : (
        <ul className="mc-scroll max-h-80 divide-y overflow-y-auto" style={{ borderColor: 'var(--border-subtle)' }}>
          {(candidates || []).map((agent) => (
            <li key={agent.AgentConfigID} className="flex items-center justify-between gap-3 py-3">
              <div className="min-w-0">
                <div className="truncate text-sm font-medium">{agent.AgentName || 'Untitled agent'}</div>
                <div className="mt-0.5 flex flex-wrap gap-1.5">
                  {agent.Mode && <Badge>{agent.Mode}</Badge>}
                  {agent.Model?.provider && <Badge>{agent.Model.provider}</Badge>}
                </div>
              </div>
              <button
                type="button"
                className="mc-btn mc-btn-secondary"
                onClick={() => claim(agent)}
                disabled={busyId === agent.AgentConfigID}
              >
                {busyId === agent.AgentConfigID ? <Spinner size={13} /> : null} Import
              </button>
            </li>
          ))}
        </ul>
      )}
    </Modal>
  )
}

export default function Agent() {
  const [agents, setAgents] = useState(null)
  const [agentsError, setAgentsError] = useState(null)
  const [config, setConfig] = useState(null)
  const [configError, setConfigError] = useState(null)
  const [credentials, setCredentials] = useState(null)

  const [form, setForm] = useState(EMPTY_FORM)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [activatingId, setActivatingId] = useState(null)
  const [newOpen, setNewOpen] = useState(false)
  const [importOpen, setImportOpen] = useState(false)

  const loadAgents = useCallback(async () => {
    setAgentsError(null)
    try {
      const data = await listAgents()
      setAgents(data.agent_configs || [])
    } catch (err) {
      setAgents([])
      setAgentsError(err.message)
    }
  }, [])

  const loadConfig = useCallback(async () => {
    setConfigError(null)
    try {
      const data = await getAgent()
      const cfg = data.agent_config || data
      const model = cfg.Model || {}
      const agent = cfg.Agent || {}
      setConfig(cfg)
      setForm({
        system_prompt: model.system_prompt || '',
        first_message: model.first_message || '',
        provider: model.provider || '',
        model: model.model || '',
        voice: model.voice || '',
        temperature: model.temperature ?? '',
        response_modality: agent.response_modality || '',
        tool_results_to_chat: Boolean(agent.tool_results_to_chat),
      })
    } catch (err) {
      setConfig(null)
      setConfigError(err.message)
    }
  }, [])

  useEffect(() => {
    loadAgents()
    loadConfig()
    getAgentCredentials().then(setCredentials).catch(() => {})
  }, [loadAgents, loadConfig])

  function update(key, value) {
    setForm((current) => ({ ...current, [key]: value }))
    setSaved(false)
  }

  async function save(event) {
    event.preventDefault()
    setSaving(true)
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
      await loadConfig()
    } catch (err) {
      setConfigError(err.message)
    } finally {
      setSaving(false)
    }
  }

  async function restoreDefaultPrompt() {
    setSaving(true)
    try {
      await updateAgent({ system_prompt: '', reset_to_default_prompt: true })
      await loadConfig()
      setSaved(true)
    } catch (err) {
      setConfigError(err.message)
    } finally {
      setSaving(false)
    }
  }

  async function activate(agentConfigId) {
    setActivatingId(agentConfigId)
    try {
      await activateAgent(agentConfigId)
      await Promise.all([loadAgents(), loadConfig()])
    } catch (err) {
      setAgentsError(err.message)
    } finally {
      setActivatingId(null)
    }
  }

  const refreshAll = () => Promise.all([loadAgents(), loadConfig()])

  return (
    <Page>
      <PageHeader
        title="Agent"
        description="The assistant MeetStream deploys into your calls — what it knows, how it sounds, and when it speaks."
        actions={
          <>
            <button type="button" className="mc-btn mc-btn-secondary" onClick={() => setImportOpen(true)}>
              Import from MeetStream
            </button>
            <button type="button" className="mc-btn mc-btn-primary" onClick={() => setNewOpen(true)}>
              <PlusIcon size={16} /> New agent
            </button>
          </>
        }
      />

      <div className="grid gap-5 lg:grid-cols-[20rem_1fr] items-start">
        <SectionCard title={`Your agents${agents ? ` (${agents.length})` : ''}`}>
          {agentsError && (
            <div className="p-4">
              <ErrorMessage title="Could not load agents" detail={agentsError} onRetry={loadAgents} />
            </div>
          )}

          {agents === null ? (
            <Loading />
          ) : agents.length === 0 ? (
            <EmptyState
              icon={<AskAiIcon size={22} />}
              title="No agents yet"
              description="Create one, or import an agent that already exists on your MeetStream account."
              action={
                <button type="button" className="mc-btn mc-btn-secondary" onClick={() => setNewOpen(true)}>
                  Create an agent
                </button>
              }
            />
          ) : (
            <ul className="divide-y" style={{ borderColor: 'var(--border-subtle)' }}>
              {agents.map((agent) => (
                <li key={agent.AgentConfigID} className="flex items-center justify-between gap-3 px-5 py-3">
                  <div className="min-w-0">
                    <div className="truncate text-sm font-medium" style={{ color: 'var(--text-strong)' }}>
                      {agent.AgentName || 'Untitled agent'}
                    </div>
                    <div className="mt-1 flex flex-wrap gap-1.5">
                      {agent.Mode && <Badge>{agent.Mode}</Badge>}
                      {agent.Model?.provider && <Badge>{agent.Model.provider}</Badge>}
                    </div>
                  </div>
                  {agent.IsActive ? (
                    <Badge tone="brand"><CheckIcon size={12} /> Active</Badge>
                  ) : (
                    <button
                      type="button"
                      className="mc-btn mc-btn-secondary"
                      onClick={() => activate(agent.AgentConfigID)}
                      disabled={activatingId === agent.AgentConfigID}
                    >
                      {activatingId === agent.AgentConfigID ? <Spinner size={13} /> : null} Use
                    </button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </SectionCard>

        <div className="min-w-0">
          {configError && !config ? (
            <Card>
              <ErrorMessage title="No agent configured" detail={configError} onRetry={loadConfig} />
              <p className="mt-4 text-sm" style={{ color: 'var(--text-muted)' }}>
                Create an agent or activate one from the list to configure it here.
              </p>
            </Card>
          ) : !config ? (
            <Card><Loading /></Card>
          ) : (
            <Card>
              <div className="mb-5 flex flex-wrap items-center gap-2">
                <h2 className="text-base font-semibold">{config.AgentName || 'Active agent'}</h2>
                {config.Mode && <Badge>{config.Mode}</Badge>}
                {config.AgentConfigID && (
                  <span className="font-mono text-[0.7rem]" style={{ color: 'var(--text-faint)' }}>
                    {config.AgentConfigID}
                  </span>
                )}
              </div>

              <form onSubmit={save}>
                <Field
                  label="System prompt"
                  hint="Controls when the agent speaks and how it answers. Resetting restores the built-in activation policy."
                  htmlFor="sys-prompt"
                >
                  <textarea
                    id="sys-prompt"
                    className="mc-input min-h-40 font-mono text-xs"
                    value={form.system_prompt}
                    onChange={(event) => update('system_prompt', event.target.value)}
                  />
                </Field>

                <Field label="First message" hint="Posted into the meeting chat when the agent joins." htmlFor="first-msg">
                  <textarea
                    id="first-msg"
                    className="mc-input min-h-20"
                    value={form.first_message}
                    onChange={(event) => update('first_message', event.target.value)}
                  />
                </Field>

                <div className="grid gap-4 sm:grid-cols-2">
                  <Field label="Provider" htmlFor="cfg-provider">
                    <input
                      id="cfg-provider"
                      className="mc-input"
                      value={form.provider}
                      onChange={(event) => update('provider', event.target.value)}
                    />
                  </Field>
                  <Field label="Model" htmlFor="cfg-model">
                    <input
                      id="cfg-model"
                      className="mc-input"
                      value={form.model}
                      onChange={(event) => update('model', event.target.value)}
                    />
                  </Field>
                  <Field label="Voice" htmlFor="cfg-voice">
                    <input
                      id="cfg-voice"
                      className="mc-input"
                      value={form.voice}
                      onChange={(event) => update('voice', event.target.value)}
                    />
                  </Field>
                  <Field label="Temperature" htmlFor="cfg-temp">
                    <input
                      id="cfg-temp"
                      type="number"
                      step="0.1"
                      className="mc-input"
                      value={form.temperature}
                      onChange={(event) => update('temperature', event.target.value)}
                    />
                  </Field>
                  <Field label="Response modality" htmlFor="cfg-modality">
                    <select
                      id="cfg-modality"
                      className="mc-input"
                      value={form.response_modality}
                      onChange={(event) => update('response_modality', event.target.value)}
                    >
                      <option value="">unchanged</option>
                      {MODALITIES.map((value) => (
                        <option key={value} value={value}>{value}</option>
                      ))}
                    </select>
                  </Field>
                </div>

                <label className="mb-5 flex items-center gap-2 text-sm" style={{ color: 'var(--text-muted)' }}>
                  <input
                    type="checkbox"
                    checked={form.tool_results_to_chat}
                    onChange={(event) => update('tool_results_to_chat', event.target.checked)}
                  />
                  Post tool results into the meeting chat
                </label>

                {configError && (
                  <div className="mb-4">
                    <ErrorMessage title="Could not save" detail={configError} />
                  </div>
                )}

                <div className="flex flex-wrap items-center gap-2">
                  <button type="submit" className="mc-btn mc-btn-primary" disabled={saving}>
                    {saving ? <Spinner size={14} /> : null} Save agent
                  </button>
                  <button
                    type="button"
                    className="mc-btn mc-btn-secondary"
                    onClick={restoreDefaultPrompt}
                    disabled={saving}
                  >
                    Reset to default prompt
                  </button>
                  {saved && <span className="text-sm" style={{ color: 'var(--color-brand-600)' }}>Saved.</span>}
                </div>
              </form>
            </Card>
          )}

          {credentials && (
            <Card className="mt-5">
              <h2 className="mb-1 text-base font-semibold">Connection</h2>
              <p className="mb-4 text-sm" style={{ color: 'var(--text-muted)' }}>
                What this workspace's agent is wired to. Secrets are shown masked.
              </p>
              <dl className="divide-y text-sm" style={{ borderColor: 'var(--border-subtle)' }}>
                {Object.entries(credentials).map(([key, value]) => (
                  <div key={key} className="flex flex-wrap justify-between gap-3 py-2.5">
                    <dt style={{ color: 'var(--text-muted)' }}>{key.replace(/_/g, ' ')}</dt>
                    <dd className="font-mono text-xs" style={{ color: 'var(--text-strong)' }}>
                      {typeof value === 'object' && value !== null
                        ? value.masked_value || (value.configured ? 'configured' : 'not set')
                        : String(value ?? '—')}
                    </dd>
                  </div>
                ))}
              </dl>
            </Card>
          )}
        </div>
      </div>

      <NewAgentModal open={newOpen} onClose={() => setNewOpen(false)} onCreated={refreshAll} />
      <ImportAgentsModal open={importOpen} onClose={() => setImportOpen(false)} onImported={refreshAll} />
    </Page>
  )
}
