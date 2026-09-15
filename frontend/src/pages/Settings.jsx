import { useEffect, useMemo, useState } from 'react'
import { Page, PageHeader } from '../components/AppShell'
import { useTheme } from '../components/AppShell'
import { Badge, Card, ConnectionBadge, ErrorMessage, Field, Loading, Spinner } from '../components/ui'
import { useIsOwner } from '../user'
import {
  clearMeetstreamApiKey,
  completeSetup,
  exportWorkspaceUrl,
  getAgentCredentials,
  getProviderCatalog,
  getSetupStatus,
  getWriteTools,
  resetSetup,
  setMeetstreamApiKey,
  setWriteTools,
  testLlmProvider,
} from '../api'
import DatabasePicker, { isDatabaseFormComplete } from '../components/DatabasePicker'
import ProviderFields from '../components/ProviderFields'

const SECTIONS = [
  { id: 'ai', label: 'AI provider' },
  { id: 'database', label: 'Database' },
  { id: 'meetings', label: 'Meetings' },
  { id: 'general', label: 'General' },
]

function EnvManagedNotice() {
  return (
    <p
      className="mb-4 rounded-lg px-3 py-2 text-xs"
      style={{ backgroundColor: 'var(--color-peach-100)', color: 'var(--color-peach-700)' }}
    >
      Some of these values are set by environment variables on this deployment and cannot be
      changed here. Update your environment and restart to change them.
    </p>
  )
}

export default function Settings() {
  const isOwner = useIsOwner()
  const [section, setSection] = useState('ai')
  const [status, setStatus] = useState(null)
  const [catalog, setCatalog] = useState(null)
  const [error, setError] = useState(null)

  const [provider, setProvider] = useState('')
  const [values, setValues] = useState({})
  const [testResult, setTestResult] = useState(null)
  const [busy, setBusy] = useState(false)
  const [saved, setSaved] = useState(false)

  const [meetstreamKey, setMeetstreamKey] = useState('')
  const [meetstreamKeyStatus, setMeetstreamKeyStatus] = useState(null)
  const [credentials, setCredentials] = useState(null)
  const [writeTools, setWriteToolsState] = useState(null)
  const [webhookSecret, setWebhookSecret] = useState('')

  const [dbProvider, setDbProvider] = useState('')
  const [dbValues, setDbValues] = useState({})
  const [dbTest, setDbTest] = useState(null)
  const [dbSaved, setDbSaved] = useState(false)
  const [dbBusy, setDbBusy] = useState(false)
  const [theme, toggleTheme] = useTheme()

  async function load() {
    try {
      const [statusData, catalogData, credentialData, writeToolsData] = await Promise.all([
        getSetupStatus(),
        getProviderCatalog(),
        getAgentCredentials().catch(() => null),
        getWriteTools().catch(() => null),
      ])
      setStatus(statusData)
      setCatalog(catalogData)
      setCredentials(credentialData)
      setWriteToolsState(writeToolsData)
      setProvider(statusData.llm?.provider || 'ollama')
      setDbProvider(statusData.database?.provider || 'sqlite')
      setValues({
        model: statusData.llm?.model || '',
        base_url: statusData.llm?.base_url || '',
        api_key: '',
      })
    } catch (err) {
      setError(err.message)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const descriptor = useMemo(
    () => catalog?.llm.find((item) => item.name === provider) || null,
    [catalog, provider],
  )

  const envManaged = status?.environment_managed || {}
  const anyEnvManaged = Object.values(envManaged).some(Boolean)

  function buildPayload() {
    return {
      provider,
      model: values.model || null,
      base_url: values.base_url || null,
      // An empty box means "leave the stored key alone" - the real key is
      // never sent to the browser, so it cannot be echoed back.
      api_key: values.api_key ? values.api_key : null,
    }
  }

  async function save() {
    setBusy(true)
    setSaved(false)
    setError(null)
    try {
      const updated = await completeSetup({ llm: buildPayload() })
      setStatus(updated)
      setValues((current) => ({ ...current, api_key: '' }))
      setSaved(true)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function runTest() {
    setBusy(true)
    setTestResult(null)
    try {
      setTestResult(await testLlmProvider(buildPayload()))
    } catch (err) {
      setTestResult({ ok: false, detail: err.message })
    } finally {
      setBusy(false)
    }
  }

  async function saveMeetstreamKey() {
    setBusy(true)
    setMeetstreamKeyStatus(null)
    try {
      const result = await setMeetstreamApiKey(meetstreamKey.trim())
      setMeetstreamKey('')
      setMeetstreamKeyStatus(
        result.connected
          ? { ok: true, detail: 'Connected to MeetStream.' }
          : { ok: false, detail: result.connection_error || 'Saved, but could not verify the connection.' },
      )
      await load()
    } catch (err) {
      setMeetstreamKeyStatus({ ok: false, detail: err.message })
    } finally {
      setBusy(false)
    }
  }

  async function handleReset() {
    if (!window.confirm('Reset configuration and return to first-run setup? Your notes and meetings are not deleted.')) {
      return
    }
    await resetSetup().catch((err) => setError(err.message))
    window.location.reload()
  }

  if (error && !status) return <Page><ErrorMessage title="Could not load settings" detail={error} /></Page>
  if (!status || !catalog) return <Page><Loading /></Page>

  return (
    <Page>
      <PageHeader title="Settings" description="Configure the infrastructure Meet Companion runs on." />

      <div className="grid gap-5 lg:grid-cols-[13rem_1fr]">
        <nav className="flex gap-1 overflow-x-auto lg:flex-col">
          {SECTIONS.map((item) => (
            <button
              key={item.id}
              type="button"
              className="mc-nav-item whitespace-nowrap"
              aria-current={section === item.id ? 'page' : undefined}
              onClick={() => setSection(item.id)}
            >
              {item.label}
            </button>
          ))}
        </nav>

        <div className="min-w-0">
          {error && (
            <div className="mb-4">
              <ErrorMessage title="Something went wrong" detail={error} />
            </div>
          )}

          {status.read_only && (section === 'ai' || section === 'database') && (
            <Card>
              <h2 className="mb-1 text-base font-semibold">Managed by a workspace owner</h2>
              <p className="text-sm" style={{ color: 'var(--text-muted)' }}>
                The AI provider ({status.llm?.provider || 'not set'}
                {status.llm?.model ? ` · ${status.llm.model}` : ''}) and database ({status.database?.provider}) are
                shared by everyone on this server. Ask an owner of your workspace to change them.
              </p>
            </Card>
          )}

          {section === 'ai' && !status.read_only && (
            <Card>
              <h2 className="mb-1 text-base font-semibold">AI provider</h2>
              <p className="mb-5 text-sm" style={{ color: 'var(--text-muted)' }}>
                Used for memory extraction and Ask AI.
              </p>

              {anyEnvManaged && <EnvManagedNotice />}

              <Field label="Provider" htmlFor="provider">
                <select
                  id="provider"
                  className="mc-input"
                  value={provider}
                  onChange={(event) => {
                    const next = catalog.llm.find((item) => item.name === event.target.value)
                    setProvider(event.target.value)
                    setTestResult(null)
                    setSaved(false)
                    // Start from the new provider's defaults - keeping the old
                    // one's host or key would send Groq requests to Ollama.
                    const defaults = {}
                    next?.fields.forEach((field) => {
                      if (field.default !== null && field.default !== undefined) defaults[field.key] = field.default
                    })
                    setValues({ model: '', base_url: '', api_key: '', ...defaults })
                  }}
                  disabled={envManaged['llm.provider']}
                >
                  {catalog.llm.map((item) => (
                    <option key={item.name} value={item.name}>{item.label}</option>
                  ))}
                </select>
              </Field>

              {descriptor && (
                <ProviderFields
                  descriptor={descriptor}
                  values={values}
                  onChange={(key, value) => {
                    setValues((current) => ({ ...current, [key]: value }))
                    setSaved(false)
                  }}
                  discoveredModels={testResult?.models || []}
                  keyHint={
                    status.llm?.api_key && status.llm?.provider === provider
                      ? `Currently set (${status.llm.api_key}). Leave blank to keep it.`
                      : undefined
                  }
                />
              )}

              <div className="flex flex-wrap items-center gap-2">
                <button type="button" className="mc-btn mc-btn-primary" onClick={save} disabled={busy}>
                  {busy ? <Spinner size={14} /> : null} Save changes
                </button>
                <button type="button" className="mc-btn mc-btn-secondary" onClick={runTest} disabled={busy}>
                  Test connection
                </button>
                {saved && <span className="text-sm" style={{ color: 'var(--color-brand-600)' }}>Saved.</span>}
                {testResult && (
                  <span
                    className="text-sm"
                    style={{ color: testResult.ok ? 'var(--color-brand-600)' : 'var(--color-rose-700)' }}
                  >
                    {testResult.ok ? 'Connected.' : testResult.detail}
                  </span>
                )}
              </div>
            </Card>
          )}

          {section === 'database' && !status.read_only && (
            <Card>
              <h2 className="mb-1 text-base font-semibold">Database</h2>
              <p className="mb-4 text-sm" style={{ color: 'var(--text-muted)' }}>
                Where meetings, notes and memory are stored. Pick any provider you like.
              </p>

              <div className="mb-5 flex flex-wrap items-center gap-2 text-sm">
                <span style={{ color: 'var(--text-muted)' }}>Currently using</span>
                <Badge tone="brand">
                  {catalog.databases.find((d) => d.name === status.database?.provider)?.label || status.database?.dialect}
                </Badge>
                <ConnectionBadge connected={status.database?.connected} />
                {status.database?.url && (
                  <code className="rounded px-1.5 py-0.5 text-xs" style={{ backgroundColor: 'var(--surface-raised)' }}>
                    {status.database.url}
                  </code>
                )}
              </div>
              {status.database?.connected === false && (
                <div className="mb-5">
                  <ErrorMessage title="The database is not answering" detail={status.database.error} onRetry={load} />
                </div>
              )}

              {status.environment_managed?.['database.url'] ? (
                <EnvManagedNotice />
              ) : (
                <>
                  <DatabasePicker
                    catalog={catalog.databases}
                    provider={dbProvider}
                    values={dbValues}
                    current={status.database?.provider}
                    connected={status.database?.connected}
                    onProviderChange={(name) => {
                      setDbProvider(name)
                      setDbSaved(false)
                    }}
                    onValuesChange={(next) => {
                      setDbValues(next)
                      setDbSaved(false)
                    }}
                    testResult={dbTest}
                    onTestResult={setDbTest}
                  />
                  <div className="mt-5 flex flex-wrap items-center gap-3">
                    <button
                      type="button"
                      className="mc-btn mc-btn-primary"
                      disabled={dbBusy || !isDatabaseFormComplete(catalog.databases.find((d) => d.name === dbProvider), dbValues)}
                      onClick={async () => {
                        setDbBusy(true)
                        setError(null)
                        try {
                          setStatus(await completeSetup({ database: { provider: dbProvider, values: dbValues } }))
                          setDbSaved(true)
                          // The new database may not know this account; the
                          // boot sequence sorts out sign-in or carries on.
                          setTimeout(() => window.location.reload(), 1200)
                        } catch (err) {
                          setError(err.message)
                        } finally {
                          setDbBusy(false)
                        }
                      }}
                    >
                      {dbBusy ? <Spinner size={14} /> : null} Save database
                    </button>
                    {dbSaved && (
                      <span className="text-sm" style={{ color: 'var(--color-brand-600)' }}>
                        Switched. Existing data is not migrated — reloading…
                      </span>
                    )}
                  </div>
                </>
              )}
            </Card>
          )}

          {section === 'meetings' && (
            <Card>
              <h2 className="mb-1 text-base font-semibold">Meeting capture</h2>
              <p className="mb-5 text-sm" style={{ color: 'var(--text-muted)' }}>
                Meet Companion uses MeetStream to send a bot into calls and produce transcripts.
                Without a key you can still use notes, search and Ask AI.
              </p>

              <Field
                label="Your MeetStream API key"
                hint={
                  credentials?.meetstream_api_key?.configured
                    ? `Currently set (${credentials.meetstream_api_key.masked_value}). Bots you launch use this key. Enter a new key to replace it.`
                    : 'Personal to you: bots you launch are created and billed under this MeetStream account.'
                }
                htmlFor="ms-key"
              >
                <input
                  id="ms-key"
                  className="mc-input"
                  type="password"
                  value={meetstreamKey}
                  onChange={(event) => {
                    setMeetstreamKey(event.target.value)
                    setMeetstreamKeyStatus(null)
                  }}
                  autoComplete="off"
                />
              </Field>

              {meetstreamKeyStatus && (
                <p
                  className="mb-3 text-sm"
                  style={{ color: meetstreamKeyStatus.ok ? 'var(--success-text, #2f9e5b)' : 'var(--danger-text, #c0392b)' }}
                >
                  {meetstreamKeyStatus.ok ? '✅' : '⚠️'} {meetstreamKeyStatus.detail}
                </p>
              )}

              <div className="flex gap-2">
                <button
                  type="button"
                  className="mc-btn mc-btn-primary"
                  onClick={saveMeetstreamKey}
                  disabled={busy || !meetstreamKey.trim()}
                >
                  Save key
                </button>
                {credentials?.meetstream_api_key?.is_personal && (
                  <button
                    type="button"
                    className="mc-btn mc-btn-danger"
                    onClick={async () => {
                      await clearMeetstreamApiKey().catch(() => {})
                      await load()
                    }}
                  >
                    Remove key
                  </button>
                )}
              </div>

              {isOwner && writeTools && (
                <>
                  <hr className="my-6" style={{ borderColor: 'var(--border-subtle)' }} />
                  <h3 className="mb-1 text-sm font-semibold">In-call agent permissions</h3>
                  <p className="mb-3 text-sm" style={{ color: 'var(--text-muted)' }}>
                    The agent always reads meeting memory. With write tools on it can also add notes and
                    create or update action items from what is said in a call — anyone in the meeting
                    can trigger that. Turn it off to keep the agent read-only.
                  </p>
                  <label className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={writeTools.enabled}
                      disabled={busy}
                      onChange={async (event) => {
                        setBusy(true)
                        try {
                          setWriteToolsState(await setWriteTools(event.target.checked))
                        } catch (err) {
                          setError(err.message)
                        } finally {
                          setBusy(false)
                        }
                      }}
                    />
                    Allow the agent to write notes and action items
                  </label>
                </>
              )}

              {isOwner && (
                <>
                  <hr className="my-6" style={{ borderColor: 'var(--border-subtle)' }} />
                  <h3 className="mb-1 text-sm font-semibold">Webhook signing secret</h3>
                  <p className="mb-4 text-sm" style={{ color: 'var(--text-muted)' }}>
                    MeetStream signs every webhook it sends with this secret, and the server rejects
                    deliveries that do not match. Set the same value in your MeetStream webhook
                    settings.{' '}
                    {status.meetstream?.webhook_secret_configured ? 'A secret is currently set.' : 'No secret is set yet - unsigned deliveries are accepted only for bots this server launched.'}
                  </p>
                  <Field label="Webhook secret" htmlFor="ms-webhook">
                    <input
                      id="ms-webhook"
                      className="mc-input"
                      type="password"
                      value={webhookSecret}
                      onChange={(event) => setWebhookSecret(event.target.value)}
                      autoComplete="off"
                      disabled={status.environment_managed?.['meetstream.webhook_secret']}
                    />
                  </Field>
                  <button
                    type="button"
                    className="mc-btn mc-btn-primary"
                    disabled={busy || !webhookSecret.trim()}
                    onClick={async () => {
                      setBusy(true)
                      try {
                        await completeSetup({ meetstream: { webhook_secret: webhookSecret.trim() } })
                        setWebhookSecret('')
                        await load()
                      } catch (err) {
                        setError(err.message)
                      } finally {
                        setBusy(false)
                      }
                    }}
                  >
                    Save secret
                  </button>
                </>
              )}
            </Card>
          )}

          {section === 'general' && (
            <div className="flex flex-col gap-4">
              <Card>
                <h2 className="mb-1 text-base font-semibold">Appearance</h2>
                <p className="mb-4 text-sm" style={{ color: 'var(--text-muted)' }}>
                  Meet Companion follows your system theme by default.
                </p>
                <button type="button" className="mc-btn mc-btn-secondary" onClick={toggleTheme}>
                  Switch to {theme === 'dark' ? 'light' : 'dark'} theme
                </button>
              </Card>

              <Card>
                <h2 className="mb-1 text-base font-semibold">Export your data</h2>
                <p className="mb-4 text-sm" style={{ color: 'var(--text-muted)' }}>
                  Everything in this workspace, in a format that outlives the app. Markdown is a
                  zip you can open as a vault (folders preserved); JSON keeps ids and metadata.
                </p>
                <div className="flex flex-wrap gap-2">
                  <a className="mc-btn mc-btn-secondary" href={exportWorkspaceUrl('md')} download>
                    Download Markdown (.zip)
                  </a>
                  <a className="mc-btn mc-btn-secondary" href={exportWorkspaceUrl('json')} download>
                    Download JSON
                  </a>
                </div>
              </Card>

              {!status.read_only && (
              <Card>
                <h2 className="mb-1 text-base font-semibold">Data management</h2>
                <p className="mb-4 text-sm" style={{ color: 'var(--text-muted)' }}>
                  Resetting configuration returns you to first-run setup. Your meetings and notes
                  are left untouched.
                </p>
                <button type="button" className="mc-btn mc-btn-danger" onClick={handleReset}>
                  Reset configuration
                </button>
              </Card>
              )}
            </div>
          )}
        </div>
      </div>
    </Page>
  )
}
