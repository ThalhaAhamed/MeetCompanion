const BASE = '/api'

async function req(path, options) {
  const res = await fetch(`${BASE}${path}`, options)
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(`${res.status} ${res.statusText}: ${body}`)
  }
  return res.json()
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
