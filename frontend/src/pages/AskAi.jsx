import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Page, PageHeader } from '../components/AppShell'
import { AskAiIcon } from '../components/Icons'
import { Badge, Card, EmptyState, ErrorMessage, Spinner } from '../components/ui'
import { askNotebook, listFolders } from '../api'

const SUGGESTIONS = [
  'What were the action items from my recent meetings?',
  'What decisions have we made about pricing?',
  'Summarise everything I have on Project Alpha.',
  'What questions are still unresolved?',
]

export default function AskAi() {
  const [question, setQuestion] = useState('')
  const [scope, setScope] = useState('all')
  const [folders, setFolders] = useState([])
  const [thread, setThread] = useState([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    listFolders()
      .then((data) => setFolders(flatten(data.folders)))
      .catch(() => {})
  }, [])

  function flatten(nodes, depth = 0, acc = []) {
    for (const node of nodes || []) {
      acc.push({ id: node.id, name: `${'— '.repeat(depth)}${node.name}` })
      flatten(node.children, depth + 1, acc)
    }
    return acc
  }

  async function ask(text) {
    const trimmed = (text ?? question).trim()
    if (!trimmed || busy) return

    setBusy(true)
    setError(null)
    setQuestion('')
    setThread((current) => [...current, { role: 'user', text: trimmed }])

    try {
      const payload = { question: trimmed }
      if (scope === 'favorites') payload.favorites_only = true
      else if (scope !== 'all') payload.folder_id = scope

      const result = await askNotebook(payload)
      setThread((current) => [
        ...current,
        { role: 'assistant', text: result.answer, sources: result.sources, model: result.model },
      ])
    } catch (err) {
      setError(err.message)
      setThread((current) => current.slice(0, -1))
      setQuestion(trimmed)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Page>
      <PageHeader
        title="Ask AI"
        description="Questions answered from your own notes and meetings, using the provider you configured."
        actions={
          <select
            className="mc-input w-auto"
            value={scope}
            onChange={(event) => setScope(event.target.value)}
            aria-label="Limit to"
          >
            <option value="all">All notes</option>
            <option value="favorites">Favourites only</option>
            {folders.map((folder) => (
              <option key={folder.id} value={folder.id}>{folder.name}</option>
            ))}
          </select>
        }
      />

      {error && (
        <div className="mb-4">
          <ErrorMessage title="Could not answer that" detail={error} />
        </div>
      )}

      <Card padded={false} className="flex min-h-[60vh] flex-col">
        <div className="mc-scroll flex-1 overflow-y-auto p-5">
          {thread.length === 0 ? (
            <EmptyState
              icon={<AskAiIcon size={22} />}
              title="Ask anything about your notes"
              description="Answers are grounded in what you have captured — nothing is invented."
              action={
                <div className="flex flex-wrap justify-center gap-2">
                  {SUGGESTIONS.map((suggestion) => (
                    <button
                      key={suggestion}
                      type="button"
                      className="mc-btn mc-btn-secondary text-xs"
                      onClick={() => ask(suggestion)}
                    >
                      {suggestion}
                    </button>
                  ))}
                </div>
              }
            />
          ) : (
            <div className="flex flex-col gap-4">
              {thread.map((entry, index) => (
                <div
                  key={index}
                  className={entry.role === 'user' ? 'self-end max-w-[80%]' : 'max-w-[85%]'}
                >
                  <div
                    className="rounded-xl px-4 py-3 text-sm leading-relaxed whitespace-pre-wrap"
                    style={
                      entry.role === 'user'
                        ? { backgroundColor: 'var(--brand-solid)', color: 'var(--text-on-brand)' }
                        : { backgroundColor: 'var(--surface-raised)', color: 'var(--text-default)' }
                    }
                  >
                    {entry.text}
                  </div>

                  {entry.sources?.length > 0 && (
                    <div className="mt-2 flex flex-wrap items-center gap-1.5">
                      <span className="text-[0.7rem]" style={{ color: 'var(--text-faint)' }}>
                        Sources:
                      </span>
                      {entry.sources.map((source) => (
                        <Link key={source.id} to={`/notebook/${source.id}`}>
                          <Badge tone="brand">{source.title}</Badge>
                        </Link>
                      ))}
                    </div>
                  )}
                </div>
              ))}
              {busy && (
                <div className="flex items-center gap-2 text-sm" style={{ color: 'var(--text-muted)' }}>
                  <Spinner size={15} /> Thinking…
                </div>
              )}
            </div>
          )}
        </div>

        <form
          className="flex gap-2 p-4"
          style={{ borderTop: '1px solid var(--border-subtle)' }}
          onSubmit={(event) => {
            event.preventDefault()
            ask()
          }}
        >
          <input
            className="mc-input"
            placeholder="Ask about your notes…"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            aria-label="Your question"
          />
          <button type="submit" className="mc-btn mc-btn-primary" disabled={busy || !question.trim()}>
            {busy ? <Spinner size={14} /> : <AskAiIcon size={16} />}
            Ask
          </button>
        </form>
      </Card>
    </Page>
  )
}
