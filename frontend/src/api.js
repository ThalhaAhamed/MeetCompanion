// In local dev, vite.config.js proxies /api to localhost:8000 - that proxy
// doesn't exist in a production static build, so a deployed frontend needs
// the real backend origin baked in at build time via VITE_API_BASE_URL.
const BASE = `${import.meta.env.VITE_API_BASE_URL || ''}/api`

async function req(path, options) {
  const res = await fetch(`${BASE}${path}`, { credentials: 'include', ...options })
  if (res.status === 401) {
    window.dispatchEvent(new Event('hub:unauthorized'))
    throw new Error('401 Unauthorized: sign-in required')
  }
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(`${res.status} ${res.statusText}: ${body}`)
  }
  return res.json()
}

export function checkAuth() {
  return req('/auth/check')
}

export function login(email, password) {
  return req('/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
}

export function logout() {
  return req('/auth/logout', { method: 'POST' })
}

export function listMembers() {
  return req('/members')
}

export function addMember({ name, email, password, workspace_name, join_code }) {
  return req('/members', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, email, password, workspace_name, join_code }),
  })
}

export function getWorkspace() {
  return req('/members/workspace')
}

export function removeMember(id) {
  return req(`/members/${id}`, { method: 'DELETE' })
}

export function resetMemberPassword(id, new_password) {
  return req(`/members/${id}/reset-password`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ new_password }),
  })
}

export function updateSelf(patch) {
  return req('/members/me', {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  })
}

export function listMeetings(day) {
  const qs = day ? `?day=${day}&limit=100` : '?limit=100'
  return req(`/meetings${qs}`)
}

export function getMeeting(id) {
  return req(`/meetings/${id}`)
}

export function getTranscript(id) {
  return req(`/meetings/${id}/transcript`)
}

export function listDocuments(day) {
  const qs = day ? `?day=${day}` : ''
  return req(`/documents${qs}`)
}

export function createMeeting({ meeting_url, title }) {
  return req('/meetings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ meeting_url, title: title || undefined }),
  })
}

export function getMeetingBot(id) {
  return req(`/meetings/${id}/bot`)
}

export function getKnowledgeGraph() {
  return req('/graph')
}

export function listImportableBots() {
  return req('/meetings/importable')
}

export function importBot({ bot_id, title, platform, meeting_url }) {
  return req('/meetings/import', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ bot_id, title, platform, meeting_url }),
  })
}

export function getAgent() {
  return req('/agent')
}

export function updateAgent(patch) {
  return req('/agent', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  })
}

export function stopMeetingBot(id) {
  return req(`/meetings/${id}/stop`, { method: 'POST' })
}

export function searchMemory(query, opts = {}) {
  return req('/search/memory', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, ...opts }),
  })
}

export function updateActionItem(id, patch) {
  return req(`/action-items/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  })
}

export function getAgentCredentials() {
  return req('/agent/credentials')
}

export function setMeetstreamApiKey(meetstream_api_key) {
  return req('/agent/api-key', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ meetstream_api_key }),
  })
}

export function clearMeetstreamApiKey() {
  return req('/agent/api-key', { method: 'DELETE' })
}

export function listAgents() {
  return req('/agent/list')
}

export function listImportableAgents() {
  return req('/agent/importable')
}

export function createAgent(payload) {
  return req('/agent', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function activateAgent(agent_config_id) {
  return req('/agent/activate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ agent_config_id }),
  })
}

export function uploadDocument(file) {
  const form = new FormData()
  form.append('file', file)
  return req('/documents/upload', { method: 'POST', body: form })
}

// ---------------------------------------------------------------------------
// Setup and configuration
// ---------------------------------------------------------------------------

export function getSetupStatus() {
  return req('/setup/status')
}

export function getProviderCatalog() {
  return req('/setup/providers')
}

export function testLlmProvider(config) {
  return req('/setup/test-llm', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  })
}

export function testDatabase(url) {
  return req('/setup/test-database', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url }),
  })
}

export function completeSetup(payload) {
  return req('/setup/complete', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function resetSetup() {
  return req('/setup/reset', { method: 'POST' })
}

// ---------------------------------------------------------------------------
// Notebook
// ---------------------------------------------------------------------------

export function listFolders() {
  return req('/notebook/folders')
}

export function createFolder({ name, parent_id = null }) {
  return req('/notebook/folders', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, parent_id }),
  })
}

export function updateFolder(id, patch) {
  return req(`/notebook/folders/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  })
}

export function deleteFolder(id, { cascade = false } = {}) {
  return req(`/notebook/folders/${id}?cascade=${cascade}`, { method: 'DELETE' })
}

export function listNotes(params = {}) {
  const query = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') query.set(key, value)
  })
  const suffix = query.toString()
  return req(`/notebook/notes${suffix ? `?${suffix}` : ''}`)
}

export function getNote(id) {
  return req(`/notebook/notes/${id}`)
}

export function createNote(payload) {
  return req('/notebook/notes', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function updateNote(id, patch) {
  return req(`/notebook/notes/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  })
}

export function deleteNote(id) {
  return req(`/notebook/notes/${id}`, { method: 'DELETE' })
}

export function listNoteTags() {
  return req('/notebook/tags')
}

export function askNotebook(payload) {
  return req('/notebook/ask', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}
