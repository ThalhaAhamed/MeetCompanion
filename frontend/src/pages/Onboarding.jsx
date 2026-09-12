import { useEffect, useMemo, useState } from 'react'
import Logo from '../components/Logo'
import { CheckIcon, ChevronRightIcon } from '../components/Icons'
import { Card, ErrorMessage, Field, Loading, Spinner } from '../components/ui'
import { completeSetup, getProviderCatalog, testLlmProvider } from '../api'
import DatabasePicker, { isDatabaseFormComplete } from '../components/DatabasePicker'

const STEPS = ['Welcome', 'AI provider', 'Storage', 'Review']

function StepRail({ current }) {
  return (
    <ol className="flex items-center gap-2 text-xs font-medium" aria-label="Setup progress">
      {STEPS.map((label, index) => {
        const done = index < current
        const active = index === current
        return (
          <li key={label} className="flex items-center gap-2">
            <span
              className="flex h-6 w-6 items-center justify-center rounded-full text-[0.7rem]"
              style={{
                backgroundColor: done || active ? 'var(--brand-solid)' : 'var(--surface-raised)',
                color: done || active ? 'var(--text-on-brand)' : 'var(--text-faint)',
              }}
            >
              {done ? <CheckIcon size={13} /> : index + 1}
            </span>
            <span style={{ color: active ? 'var(--text-strong)' : 'var(--text-faint)' }}>{label}</span>
            {index < STEPS.length - 1 && (
              <ChevronRightIcon size={14} style={{ color: 'var(--text-faint)' }} />
            )}
          </li>
        )
      })}
    </ol>
  )
}

function ProviderOption({ descriptor, selected, onSelect }) {
  return (
    <button
      type="button"
      onClick={() => onSelect(descriptor.name)}
      className="w-full rounded-xl p-4 text-left transition-colors"
      style={{
        border: `1px solid ${selected ? 'var(--brand-ring)' : 'var(--border-subtle)'}`,
        backgroundColor: selected ? 'var(--brand-soft)' : 'var(--surface-panel)',
        boxShadow: selected ? '0 0 0 3px color-mix(in srgb, var(--brand-ring) 20%, transparent)' : 'none',
      }}
      aria-pressed={selected}
    >
      <div className="flex items-center justify-between gap-3">
        <span className="font-medium" style={{ color: 'var(--text-strong)' }}>
          {descriptor.label}
        </span>
        {descriptor.local && (
          <span
            className="mc-badge"
            style={{ backgroundColor: 'var(--color-peach-200)', color: 'var(--color-peach-700)', borderColor: 'transparent' }}
          >
            Runs locally
          </span>
        )}
      </div>
      <p className="mt-1 text-sm" style={{ color: 'var(--text-muted)' }}>
        {descriptor.summary}
      </p>
    </button>
  )
}

/** Renders exactly the fields a provider declares, and nothing else. */
function DynamicFields({ fields, values, onChange }) {
  return (
    <>
      {fields.map((field) => (
        <Field
          key={field.key}
          label={field.label}
          hint={field.help}
          htmlFor={`field-${field.key}`}
        >
          <input
            id={`field-${field.key}`}
            className="mc-input"
            type={field.type === 'password' ? 'password' : field.type === 'number' ? 'number' : 'text'}
            step={field.type === 'number' ? '0.1' : undefined}
            placeholder={field.placeholder || ''}
            value={values[field.key] ?? ''}
            onChange={(event) => onChange(field.key, event.target.value)}
            autoComplete={field.type === 'password' ? 'off' : undefined}
          />
        </Field>
      ))}
    </>
  )
}

export default function Onboarding({ onComplete }) {
  const [step, setStep] = useState(0)
  const [catalog, setCatalog] = useState(null)
  const [loadError, setLoadError] = useState(null)

  const [provider, setProvider] = useState('ollama')
  const [values, setValues] = useState({})
  const [llmTest, setLlmTest] = useState(null)
  const [testing, setTesting] = useState(false)

  const [storage, setStorage] = useState('')
  const [dbValues, setDbValues] = useState({})
  const [dbTest, setDbTest] = useState(null)

  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState(null)

  useEffect(() => {
    getProviderCatalog()
      .then(setCatalog)
      .catch((error) => setLoadError(error.message))
  }, [])

  const descriptor = useMemo(
    () => catalog?.llm.find((item) => item.name === provider) || null,
    [catalog, provider],
  )

  // Reset to the newly chosen provider's defaults, so switching never leaves
  // a stale key or host from the previous one behind.
  useEffect(() => {
    if (!descriptor) return
    const defaults = {}
    descriptor.fields.forEach((field) => {
      if (field.default !== null && field.default !== undefined) defaults[field.key] = field.default
    })
    setValues(defaults)
    setLlmTest(null)
  }, [descriptor])

  function updateValue(key, value) {
    setValues((current) => ({ ...current, [key]: value }))
    setLlmTest(null)
  }

  function buildLlmPayload() {
    return {
      provider,
      model: values.model || null,
      api_key: values.api_key || null,
      base_url: values.base_url || null,
      temperature: values.temperature ? Number(values.temperature) : null,
    }
  }

  async function runLlmTest() {
    setTesting(true)
    setLlmTest(null)
    try {
      setLlmTest(await testLlmProvider(buildLlmPayload()))
    } catch (error) {
      setLlmTest({ ok: false, detail: error.message })
    } finally {
      setTesting(false)
    }
  }

  async function finish() {
    setSaving(true)
    setSaveError(null)
    try {
      await completeSetup({
        llm: buildLlmPayload(),
        database: { provider: storage, values: dbValues },
      })
      onComplete?.()
    } catch (error) {
      setSaveError(error.message)
    } finally {
      setSaving(false)
    }
  }

  if (loadError) {
    return (
      <div className="mx-auto max-w-lg px-5 py-20">
        <ErrorMessage
          title="Could not reach the Meet Companion server"
          detail={loadError}
          onRetry={() => window.location.reload()}
        />
      </div>
    )
  }

  if (!catalog) {
    return <Loading label="Preparing setup…" />
  }

  const canContinueFromProvider =
    Boolean(values.model) &&
    descriptor.fields
      .filter((field) => field.required)
      .every((field) => String(values[field.key] ?? '').trim().length > 0)

  const dbEntry = catalog.databases.find((item) => item.name === storage)
  const canFinish = isDatabaseFormComplete(dbEntry, dbValues)

  return (
    <div className="min-h-screen" style={{ backgroundColor: 'var(--surface-page)' }}>
      <div className="mx-auto w-full max-w-2xl px-5 py-12">
        <div className="mb-8 flex justify-center">
          <StepRail current={step} />
        </div>

        {step === 0 && (
          <Card className="text-center">
            <div className="flex flex-col items-center py-6">
              <Logo variant="icon" size={84} />
              <h1 className="mt-6 text-3xl font-semibold">Meet Companion</h1>
              <p
                className="mt-2 text-xs font-semibold uppercase tracking-[0.22em]"
                style={{ color: 'var(--text-faint)' }}
              >
                Make meeting data smarter.
              </p>
              <p className="mt-6 max-w-md text-sm leading-relaxed" style={{ color: 'var(--text-muted)' }}>
                Your open-source AI meeting companion. Choose your own AI models, storage and
                infrastructure — nothing is locked to a vendor, and nothing leaves your machine
                unless you configure it to.
              </p>
              <button type="button" className="mc-btn mc-btn-primary mt-8" onClick={() => setStep(1)}>
                Get started
                <ChevronRightIcon size={16} />
              </button>
            </div>
          </Card>
        )}

        {step === 1 && (
          <Card>
            <h2 className="text-lg font-semibold">Choose your AI provider</h2>
            <p className="mt-1 mb-5 text-sm" style={{ color: 'var(--text-muted)' }}>
              Used to extract decisions and action items from meetings, and to answer questions
              about your notes. You can change this later in Settings.
            </p>

            <div className="grid gap-2 sm:grid-cols-2">
              {catalog.llm.map((item) => (
                <ProviderOption
                  key={item.name}
                  descriptor={item}
                  selected={item.name === provider}
                  onSelect={setProvider}
                />
              ))}
            </div>

            {descriptor && (
              <div className="mt-6 border-t pt-5" style={{ borderColor: 'var(--border-subtle)' }}>
                <DynamicFields fields={descriptor.fields} values={values} onChange={updateValue} />

                {descriptor.suggested_models?.length > 0 && (
                  <div className="-mt-2 mb-4 flex flex-wrap gap-1.5">
                    {descriptor.suggested_models.map((model) => (
                      <button
                        key={model}
                        type="button"
                        className="mc-badge"
                        onClick={() => updateValue('model', model)}
                      >
                        {model}
                      </button>
                    ))}
                  </div>
                )}

                <div className="flex items-center gap-3">
                  <button
                    type="button"
                    className="mc-btn mc-btn-secondary"
                    onClick={runLlmTest}
                    disabled={testing}
                  >
                    {testing ? <Spinner size={14} /> : null}
                    Test connection
                  </button>
                  {llmTest && (
                    <span
                      className="text-sm"
                      style={{ color: llmTest.ok ? 'var(--color-brand-600)' : 'var(--color-rose-700)' }}
                    >
                      {llmTest.ok ? 'Connected.' : llmTest.detail}
                    </span>
                  )}
                </div>
              </div>
            )}

            <div className="mt-6 flex justify-between">
              <button type="button" className="mc-btn mc-btn-ghost" onClick={() => setStep(0)}>
                Back
              </button>
              <button
                type="button"
                className="mc-btn mc-btn-primary"
                onClick={() => setStep(2)}
                disabled={!canContinueFromProvider}
              >
                Continue
                <ChevronRightIcon size={16} />
              </button>
            </div>
          </Card>
        )}

        {step === 2 && (
          <Card>
            <h2 className="text-lg font-semibold">Where should Meet Companion store your data?</h2>
            <p className="mt-1 mb-5 text-sm" style={{ color: 'var(--text-muted)' }}>
              Meetings, notes and memory all live here.
            </p>

            <DatabasePicker
              catalog={catalog.databases}
              provider={storage}
              values={dbValues}
              onProviderChange={setStorage}
              onValuesChange={setDbValues}
              testResult={dbTest}
              onTestResult={setDbTest}
            />

            <div className="mt-6 flex justify-between">
              <button type="button" className="mc-btn mc-btn-ghost" onClick={() => setStep(1)}>
                Back
              </button>
              <button
                type="button"
                className="mc-btn mc-btn-primary"
                onClick={() => setStep(3)}
                disabled={!canFinish}
              >
                Continue
                <ChevronRightIcon size={16} />
              </button>
            </div>
          </Card>
        )}

        {step === 3 && (
          <Card>
            <h2 className="text-lg font-semibold">Review your setup</h2>
            <p className="mt-1 mb-5 text-sm" style={{ color: 'var(--text-muted)' }}>
              You can change any of this later in Settings.
            </p>

            <dl className="divide-y" style={{ borderColor: 'var(--border-subtle)' }}>
              <div className="flex justify-between gap-4 py-3">
                <dt className="text-sm" style={{ color: 'var(--text-muted)' }}>AI provider</dt>
                <dd className="text-sm font-medium">{descriptor?.label}</dd>
              </div>
              <div className="flex justify-between gap-4 py-3">
                <dt className="text-sm" style={{ color: 'var(--text-muted)' }}>Model</dt>
                <dd className="text-sm font-medium">{values.model || '—'}</dd>
              </div>
              {values.base_url && (
                <div className="flex justify-between gap-4 py-3">
                  <dt className="text-sm" style={{ color: 'var(--text-muted)' }}>Endpoint</dt>
                  <dd className="truncate text-sm font-medium">{values.base_url}</dd>
                </div>
              )}
              <div className="flex justify-between gap-4 py-3">
                <dt className="text-sm" style={{ color: 'var(--text-muted)' }}>Storage</dt>
                <dd className="text-sm font-medium">
                  {dbEntry?.label || storage}
                </dd>
              </div>
            </dl>

            {saveError && (
              <div className="mt-4">
                <ErrorMessage title="Could not save your setup" detail={saveError} />
              </div>
            )}

            <div className="mt-6 flex justify-between">
              <button type="button" className="mc-btn mc-btn-ghost" onClick={() => setStep(2)}>
                Back
              </button>
              <button
                type="button"
                className="mc-btn mc-btn-primary"
                onClick={finish}
                disabled={saving}
              >
                {saving ? <Spinner size={14} /> : null}
                Finish setup
              </button>
            </div>
          </Card>
        )}
      </div>
    </div>
  )
}
