// In local dev, vite.config.js proxies /api to localhost:8000 - that proxy
// doesn't exist in a production static build, so a deployed frontend needs
// the real backend origin baked in at build time via VITE_API_BASE_URL.
const BASE = `${import.meta.env.VITE_API_BASE_URL || ''}/api`

async function req(path, options) {
  const res = await fetch(`${BASE}${path}`, { credentials: 'include', ...options })
  if (res.status === 401) {
    window.dispatchEvent(new Event('hub:unauthorized'))
    throw new Error('401 Unauthorized: passphrase required')
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

export function getBootstrapStatus() {
  return req('/members/bootstrap-status')
}

export function listMembers() {
  return req('/members')
}

export function addMember({ name, email, password, passphrase }) {
  return req('/members', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, email, password, passphrase }),
  })
}

export function removeMember(id) {
  return req(`/members/${id}`, { method: 'DELETE' })
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

export function listAgents() {
  return req('/agent/list')
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
