import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  ChevronDownIcon,
  ChevronRightIcon,
  FolderIcon,
  FolderOpenIcon,
  NoteIcon,
  PlusIcon,
  SearchIcon,
  StarIcon,
  TrashIcon,
} from '../components/Icons'
import { Badge, EmptyState, ErrorMessage, Loading, Modal, Spinner } from '../components/ui'
import {
  createFolder,
  createNote,
  deleteFolder,
  deleteNote,
  getNote,
  listFolders,
  listNoteTags,
  listNotes,
  updateNote,
} from '../api'

const SORTS = [
  { value: 'updated', label: 'Last updated' },
  { value: 'created', label: 'Date created' },
  { value: 'title', label: 'Title' },
]

const NOTE_TYPES = ['note', 'meeting', 'idea', 'research']

const SAVE_DEBOUNCE_MS = 800

function FolderRow({ node, depth, selectedId, onSelect, onContextMenu }) {
  const [open, setOpen] = useState(depth < 1)
  const hasChildren = node.children?.length > 0
  const selected = selectedId === node.id

  return (
    <div>
      <div
        className="mc-nav-item group cursor-pointer"
        style={{ paddingLeft: `${0.5 + depth * 0.85}rem` }}
        aria-current={selected ? 'page' : undefined}
        onClick={() => onSelect(node.id)}
      >
        <button
          type="button"
          className="shrink-0"
          style={{ visibility: hasChildren ? 'visible' : 'hidden' }}
          onClick={(event) => {
            event.stopPropagation()
            setOpen((v) => !v)
          }}
          aria-label={open ? 'Collapse folder' : 'Expand folder'}
        >
          {open ? <ChevronDownIcon size={14} /> : <ChevronRightIcon size={14} />}
        </button>
        {open && hasChildren ? <FolderOpenIcon size={16} /> : <FolderIcon size={16} />}
        <span className="flex-1 truncate">{node.name}</span>
        {node.note_count > 0 && (
          <span className="text-[0.7rem]" style={{ color: 'var(--text-faint)' }}>
            {node.note_count}
          </span>
        )}
        <button
          type="button"
          className="opacity-0 transition-opacity group-hover:opacity-100"
          onClick={(event) => {
            event.stopPropagation()
            onContextMenu(node)
          }}
          aria-label={`Manage folder ${node.name}`}
        >
          <TrashIcon size={14} />
        </button>
      </div>

      {open &&
        node.children?.map((child) => (
          <FolderRow
            key={child.id}
            node={child}
            depth={depth + 1}
            selectedId={selectedId}
            onSelect={onSelect}
            onContextMenu={onContextMenu}
          />
        ))}
    </div>
  )
}

function NoteEditor({ note, onChange, onDelete, saving }) {
  const [draft, setDraft] = useState(note)
  const timer = useRef(null)

  useEffect(() => {
    setDraft(note)
  }, [note.id])

  // Debounced autosave: typing should not fire a request per keystroke, but
  // the user should never have to remember to press save.
  const queueSave = useCallback(
    (patch) => {
      if (timer.current) clearTimeout(timer.current)
      timer.current = setTimeout(() => onChange(patch), SAVE_DEBOUNCE_MS)
    },
    [onChange],
  )

  useEffect(() => () => timer.current && clearTimeout(timer.current), [])

  function edit(key, value) {
    setDraft((current) => ({ ...current, [key]: value }))
    queueSave({ [key]: value })
  }

  return (
    <div className="flex h-full flex-col">
      <div
        className="flex items-center gap-2 px-5 py-3"
        style={{ borderBottom: '1px solid var(--border-subtle)' }}
      >
        <input
          className="mc-input border-transparent bg-transparent px-0 text-lg font-semibold"
          value={draft.title}
          onChange={(event) => edit('title', event.target.value)}
          placeholder="Untitled"
          aria-label="Note title"
        />
        <button
          type="button"
          className="mc-btn mc-btn-ghost px-2"
          onClick={() => onChange({ is_favorite: !draft.is_favorite })}
          aria-label={draft.is_favorite ? 'Remove from favourites' : 'Add to favourites'}
          title={draft.is_favorite ? 'Remove from favourites' : 'Add to favourites'}
          style={{ color: draft.is_favorite ? 'var(--color-peach-500)' : undefined }}
        >
          <StarIcon size={17} filled={draft.is_favorite} />
        </button>
        <button
          type="button"
          className="mc-btn mc-btn-ghost px-2"
          onClick={onDelete}
          aria-label="Delete note"
          title="Delete note"
        >
          <TrashIcon size={17} />
        </button>
      </div>

      <div
        className="flex flex-wrap items-center gap-2 px-5 py-2.5 text-xs"
        style={{ borderBottom: '1px solid var(--border-subtle)', color: 'var(--text-muted)' }}
      >
        <select
          className="mc-input w-auto py-1 text-xs"
          value={draft.note_type}
          onChange={(event) => edit('note_type', event.target.value)}
          aria-label="Note type"
        >
          {NOTE_TYPES.map((type) => (
            <option key={type} value={type}>
              {type}
            </option>
          ))}
        </select>

        <input
          className="mc-input w-auto flex-1 py-1 text-xs"
          placeholder="Tags, comma separated"
          value={(draft.tags || []).join(', ')}
          onChange={(event) =>
            edit(
              'tags',
              event.target.value
                .split(',')
                .map((tag) => tag.trim())
                .filter(Boolean),
            )
          }
          aria-label="Tags"
        />

        <span style={{ color: 'var(--text-faint)' }}>
          {saving ? 'Saving…' : draft.updated_at ? `Saved ${new Date(draft.updated_at).toLocaleString()}` : ''}
        </span>
      </div>

      <textarea
        className="mc-scroll flex-1 resize-none bg-transparent px-5 py-4 text-sm leading-relaxed outline-none"
        style={{ color: 'var(--text-default)' }}
        value={draft.content || ''}
        onChange={(event) => edit('content', event.target.value)}
        placeholder="Start writing…"
        aria-label="Note content"
      />
    </div>
  )
}

export default function Notebook() {
  const { noteId } = useParams()
  const navigate = useNavigate()

  const [tree, setTree] = useState(null)
  const [counts, setCounts] = useState({})
  const [notes, setNotes] = useState([])
  const [total, setTotal] = useState(0)
  const [tags, setTags] = useState([])
  const [active, setActive] = useState(null)
  const [error, setError] = useState(null)
  const [loadingList, setLoadingList] = useState(true)
  const [saving, setSaving] = useState(false)

  const [scope, setScope] = useState({ kind: 'all' })
  const [query, setQuery] = useState('')
  const [sort, setSort] = useState('updated')
  const [tagFilter, setTagFilter] = useState('')
  const [newFolderOpen, setNewFolderOpen] = useState(false)
  const [newFolderName, setNewFolderName] = useState('')
  const [folderToDelete, setFolderToDelete] = useState(null)

  const refreshFolders = useCallback(async () => {
    const data = await listFolders()
    setTree(data.folders)
    setCounts(data.counts || {})
  }, [])

  const refreshNotes = useCallback(async () => {
    setLoadingList(true)
    try {
      const params = { sort, limit: 200 }
      if (query.trim()) params.q = query.trim()
      if (tagFilter) params.tag = tagFilter
      if (scope.kind === 'folder') params.folder_id = scope.id
      if (scope.kind === 'unfiled') params.unfiled = true
      if (scope.kind === 'favorites') params.favorites_only = true

      const data = await listNotes(params)
      setNotes(data.notes)
      setTotal(data.total)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoadingList(false)
    }
  }, [query, sort, tagFilter, scope])

  useEffect(() => {
    refreshFolders().catch((err) => setError(err.message))
    listNoteTags()
      .then((data) => setTags(data.tags))
      .catch(() => {})
  }, [refreshFolders])

  // Debounced so typing in search does not fire a request per keystroke.
  useEffect(() => {
    const handle = setTimeout(() => {
      refreshNotes()
    }, 220)
    return () => clearTimeout(handle)
  }, [refreshNotes])

  useEffect(() => {
    if (!noteId) {
      setActive(null)
      return
    }
    getNote(noteId)
      .then(setActive)
      .catch(() => navigate('/notebook', { replace: true }))
  }, [noteId, navigate])

  async function handleCreateNote() {
    const payload = { title: 'Untitled', content: '' }
    if (scope.kind === 'folder') payload.folder_id = scope.id
    const created = await createNote(payload)
    await Promise.all([refreshNotes(), refreshFolders()])
    navigate(`/notebook/${created.id}`)
  }

  async function handleUpdateNote(patch) {
    if (!active) return
    setSaving(true)
    try {
      const updated = await updateNote(active.id, patch)
      setActive(updated)
      await Promise.all([refreshNotes(), refreshFolders()])
      listNoteTags().then((data) => setTags(data.tags)).catch(() => {})
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  async function handleDeleteNote() {
    if (!active) return
    await deleteNote(active.id)
    navigate('/notebook')
    await Promise.all([refreshNotes(), refreshFolders()])
  }

  async function handleCreateFolder() {
    if (!newFolderName.trim()) return
    await createFolder({
      name: newFolderName.trim(),
      parent_id: scope.kind === 'folder' ? scope.id : null,
    })
    setNewFolderName('')
    setNewFolderOpen(false)
    await refreshFolders()
  }

  async function handleDeleteFolder(cascade) {
    await deleteFolder(folderToDelete.id, { cascade })
    setFolderToDelete(null)
    if (scope.kind === 'folder' && scope.id === folderToDelete.id) setScope({ kind: 'all' })
    await Promise.all([refreshFolders(), refreshNotes()])
  }

  const scopeLabel = useMemo(() => {
    if (scope.kind === 'favorites') return 'Favourites'
    if (scope.kind === 'unfiled') return 'Unfiled'
    if (scope.kind === 'folder') return 'Folder'
    return 'All notes'
  }, [scope])

  if (error) {
    return (
      <div className="p-8">
        <ErrorMessage title="Notebook unavailable" detail={error} onRetry={() => window.location.reload()} />
      </div>
    )
  }

  return (
    <div className="flex h-screen">
      {/* Folder tree */}
      <div
        className="hidden w-60 shrink-0 flex-col lg:flex"
        style={{ borderRight: '1px solid var(--border-subtle)', backgroundColor: 'var(--surface-nav)' }}
      >
        <div className="flex items-center justify-between px-4 py-4">
          <h2 className="text-sm font-semibold">Notebook</h2>
          <button
            type="button"
            className="mc-btn mc-btn-ghost px-2"
            onClick={() => setNewFolderOpen(true)}
            title="New folder"
            aria-label="New folder"
          >
            <PlusIcon size={16} />
          </button>
        </div>

        <div className="mc-scroll flex-1 overflow-y-auto px-2 pb-4">
          <div
            className="mc-nav-item cursor-pointer"
            aria-current={scope.kind === 'all' ? 'page' : undefined}
            onClick={() => setScope({ kind: 'all' })}
          >
            <NoteIcon size={16} />
            <span className="flex-1">All notes</span>
            <span className="text-[0.7rem]" style={{ color: 'var(--text-faint)' }}>{counts.total ?? 0}</span>
          </div>
          <div
            className="mc-nav-item cursor-pointer"
            aria-current={scope.kind === 'favorites' ? 'page' : undefined}
            onClick={() => setScope({ kind: 'favorites' })}
          >
            <StarIcon size={16} />
            <span className="flex-1">Favourites</span>
            <span className="text-[0.7rem]" style={{ color: 'var(--text-faint)' }}>{counts.favorites ?? 0}</span>
          </div>
          <div
            className="mc-nav-item cursor-pointer"
            aria-current={scope.kind === 'unfiled' ? 'page' : undefined}
            onClick={() => setScope({ kind: 'unfiled' })}
          >
            <FolderIcon size={16} />
            <span className="flex-1">Unfiled</span>
            <span className="text-[0.7rem]" style={{ color: 'var(--text-faint)' }}>{counts.unfiled ?? 0}</span>
          </div>

          <div
            className="mt-4 mb-1 px-3 text-[0.65rem] font-semibold uppercase tracking-[0.14em]"
            style={{ color: 'var(--text-faint)' }}
          >
            Folders
          </div>

          {tree === null ? (
            <div className="px-3 py-2"><Spinner size={14} /></div>
          ) : tree.length === 0 ? (
            <p className="px-3 py-2 text-xs" style={{ color: 'var(--text-faint)' }}>
              No folders yet.
            </p>
          ) : (
            tree.map((node) => (
              <FolderRow
                key={node.id}
                node={node}
                depth={0}
                selectedId={scope.kind === 'folder' ? scope.id : null}
                onSelect={(id) => setScope({ kind: 'folder', id })}
                onContextMenu={setFolderToDelete}
              />
            ))
          )}
        </div>
      </div>

      {/* Note list */}
      <div
        className="flex w-full shrink-0 flex-col md:w-80"
        style={{ borderRight: '1px solid var(--border-subtle)', backgroundColor: 'var(--surface-panel)' }}
      >
        <div className="px-4 py-3" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
          <div className="mb-2 flex items-center justify-between">
            <span className="text-sm font-semibold">{scopeLabel}</span>
            <button type="button" className="mc-btn mc-btn-primary px-2 py-1" onClick={handleCreateNote}>
              <PlusIcon size={15} /> New
            </button>
          </div>

          <div className="relative">
            <span className="absolute left-2.5 top-2.5" style={{ color: 'var(--text-faint)' }}>
              <SearchIcon size={15} />
            </span>
            <input
              className="mc-input pl-8 text-sm"
              placeholder="Search notes…"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              aria-label="Search notes"
            />
          </div>

          <div className="mt-2 flex gap-1.5">
            <select
              className="mc-input py-1 text-xs"
              value={sort}
              onChange={(event) => setSort(event.target.value)}
              aria-label="Sort notes"
            >
              {SORTS.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
            <select
              className="mc-input py-1 text-xs"
              value={tagFilter}
              onChange={(event) => setTagFilter(event.target.value)}
              aria-label="Filter by tag"
            >
              <option value="">All tags</option>
              {tags.map((tag) => (
                <option key={tag} value={tag}>{tag}</option>
              ))}
            </select>
          </div>

          {(query || tagFilter || scope.kind !== 'all') && (
            <button
              type="button"
              className="mt-2 text-xs"
              style={{ color: 'var(--brand-soft-text)' }}
              onClick={() => {
                setQuery('')
                setTagFilter('')
                setScope({ kind: 'all' })
              }}
            >
              Clear filters · {total} match{total === 1 ? '' : 'es'}
            </button>
          )}
        </div>

        <div className="mc-scroll flex-1 overflow-y-auto">
          {loadingList ? (
            <Loading />
          ) : notes.length === 0 ? (
            <EmptyState
              icon={<NoteIcon size={22} />}
              title={query || tagFilter ? 'No matching notes' : 'No notes yet'}
              description={
                query || tagFilter
                  ? 'Try a different search or clear your filters.'
                  : 'Create your first note to get started.'
              }
              action={
                !query && !tagFilter ? (
                  <button type="button" className="mc-btn mc-btn-secondary" onClick={handleCreateNote}>
                    New note
                  </button>
                ) : null
              }
            />
          ) : (
            <ul className="divide-y" style={{ borderColor: 'var(--border-subtle)' }}>
              {notes.map((note) => (
                <li key={note.id}>
                  <button
                    type="button"
                    className="w-full px-4 py-3 text-left transition-colors hover:bg-[var(--surface-raised)]"
                    style={{
                      backgroundColor: note.id === noteId ? 'var(--brand-soft)' : undefined,
                    }}
                    onClick={() => navigate(`/notebook/${note.id}`)}
                  >
                    <div className="flex items-start gap-2">
                      <span className="min-w-0 flex-1 truncate text-sm font-medium" style={{ color: 'var(--text-strong)' }}>
                        {note.title}
                      </span>
                      {note.is_favorite && (
                        <StarIcon size={13} filled style={{ color: 'var(--color-peach-500)' }} />
                      )}
                    </div>
                    {note.excerpt && (
                      <p className="mt-0.5 line-clamp-2 text-xs" style={{ color: 'var(--text-muted)' }}>
                        {note.excerpt}
                      </p>
                    )}
                    <div className="mt-1.5 flex flex-wrap items-center gap-1">
                      {(note.tags || []).slice(0, 3).map((tag) => (
                        <Badge key={tag}>{tag}</Badge>
                      ))}
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {/* Editor */}
      <div className="hidden min-w-0 flex-1 md:block" style={{ backgroundColor: 'var(--surface-panel)' }}>
        {active ? (
          <NoteEditor
            key={active.id}
            note={active}
            onChange={handleUpdateNote}
            onDelete={handleDeleteNote}
            saving={saving}
          />
        ) : (
          <EmptyState
            icon={<NoteIcon size={22} />}
            title="Select a note"
            description="Choose a note from the list, or create a new one."
          />
        )}
      </div>

      <Modal
        open={newFolderOpen}
        onClose={() => setNewFolderOpen(false)}
        title="New folder"
        footer={
          <>
            <button type="button" className="mc-btn mc-btn-secondary" onClick={() => setNewFolderOpen(false)}>
              Cancel
            </button>
            <button type="button" className="mc-btn mc-btn-primary" onClick={handleCreateFolder}>
              Create
            </button>
          </>
        }
      >
        <input
          className="mc-input"
          autoFocus
          placeholder="Folder name"
          value={newFolderName}
          onChange={(event) => setNewFolderName(event.target.value)}
          onKeyDown={(event) => event.key === 'Enter' && handleCreateFolder()}
          aria-label="Folder name"
        />
      </Modal>

      <Modal
        open={Boolean(folderToDelete)}
        onClose={() => setFolderToDelete(null)}
        title={`Delete "${folderToDelete?.name || ''}"`}
        footer={
          <>
            <button type="button" className="mc-btn mc-btn-secondary" onClick={() => setFolderToDelete(null)}>
              Cancel
            </button>
            <button type="button" className="mc-btn mc-btn-secondary" onClick={() => handleDeleteFolder(false)}>
              Keep notes
            </button>
            <button type="button" className="mc-btn mc-btn-danger" onClick={() => handleDeleteFolder(true)}>
              Delete everything
            </button>
          </>
        }
      >
        <p className="text-sm" style={{ color: 'var(--text-muted)' }}>
          <strong>Keep notes</strong> moves this folder's notes and subfolders up one level.{' '}
          <strong>Delete everything</strong> permanently removes the folder and all of its contents.
        </p>
      </Modal>
    </div>
  )
}
