import { useEffect, useState } from 'react'
import { getMeeting, getTranscript, getMeetingBot } from './api'

export default function MeetingDetail({ meetingId }) {
  const [meeting, setMeeting] = useState(null)
  const [transcript, setTranscript] = useState([])
  const [tab, setTab] = useState('summary')
  const [error, setError] = useState(null)
  const [bot, setBot] = useState(null)
  const [botError, setBotError] = useState(null)
  const [botLoading, setBotLoading] = useState(false)

  useEffect(() => {
    setMeeting(null)
    setTranscript([])
    setError(null)
    setTab('summary')
    setBot(null)
    setBotError(null)
    Promise.all([getMeeting(meetingId), getTranscript(meetingId)])
      .then(([m, t]) => {
        setMeeting(m)
        setTranscript(t)
      })
      .catch((e) => setError(e.message))
  }, [meetingId])

  useEffect(() => {
    if (tab !== 'bot' || bot || botLoading) return
    setBotLoading(true)
    setBotError(null)
    getMeetingBot(meetingId)
      .then(setBot)
      .catch((e) => setBotError(e.message))
      .finally(() => setBotLoading(false))
  }, [tab, meetingId, bot, botLoading])

  if (error) return <div className="error">Failed to load meeting: {error}</div>
  if (!meeting) return <div className="loading">Loading meeting…</div>

  return (
    <div className="meeting-detail">
      <h2>{meeting.title || 'Untitled meeting'}</h2>
      <div className="detail-meta">
        <span className={`badge status-${meeting.status}`}>{meeting.status}</span>
        {meeting.customer_name && <span className="tag">{meeting.customer_name}</span>}
        {meeting.project_name && <span className="tag">{meeting.project_name}</span>}
        {meeting.platform && <span className="tag">{meeting.platform}</span>}
      </div>

      <div className="tabs">
        <button className={tab === 'summary' ? 'active' : ''} onClick={() => setTab('summary')}>
          Summary
        </button>
        <button className={tab === 'memories' ? 'active' : ''} onClick={() => setTab('memories')}>
          Decisions & Memories ({meeting.memories.length})
        </button>
        <button className={tab === 'actions' ? 'active' : ''} onClick={() => setTab('actions')}>
          Action Items ({meeting.action_items.length})
        </button>
        <button className={tab === 'transcript' ? 'active' : ''} onClick={() => setTab('transcript')}>
          Transcript ({transcript.length})
        </button>
        <button className={tab === 'bot' ? 'active' : ''} onClick={() => setTab('bot')}>
          Bot
        </button>
      </div>

      {tab === 'summary' && (
        <div className="tab-panel">
          {meeting.summary ? <p>{meeting.summary}</p> : <p className="empty">No summary generated yet.</p>}
          <h3>Participants</h3>
          {meeting.participants.length === 0 ? (
            <p className="empty">No participants recorded.</p>
          ) : (
            <ul className="participants">
              {meeting.participants.map((p) => (
                <li key={p.id}>{p.name || p.identifier || 'Unknown'}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      {tab === 'memories' && (
        <div className="tab-panel">
          {meeting.memories.length === 0 ? (
            <p className="empty">No memories extracted.</p>
          ) : (
            <ul className="memories">
              {meeting.memories.map((mem) => (
                <li key={mem.id} className="memory-item">
                  <span className="badge">{mem.type}</span>
                  <p>{mem.content}</p>
                  {mem.speaker && <span className="time">— {mem.speaker}</span>}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {tab === 'actions' && (
        <div className="tab-panel">
          {meeting.action_items.length === 0 ? (
            <p className="empty">No action items.</p>
          ) : (
            <ul className="actions">
              {meeting.action_items.map((a) => (
                <li key={a.id} className="action-item">
                  <span className={`badge status-${a.status}`}>{a.status}</span>
                  <p>{a.task}</p>
                  <div className="list-item-meta">
                    {a.owner && <span className="tag">{a.owner}</span>}
                    {a.due_date && <span className="tag">due {a.due_date}</span>}
                    <span className="tag">{a.priority}</span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {tab === 'transcript' && (
        <div className="tab-panel transcript">
          {transcript.length === 0 ? (
            <p className="empty">No transcript captured.</p>
          ) : (
            transcript.map((seg) => (
              <div key={seg.id} className="transcript-line">
                <span className="speaker">{seg.speaker || 'Unknown'}</span>
                <span className="text">{seg.text}</span>
              </div>
            ))
          )}
        </div>
      )}

      {tab === 'bot' && (
        <div className="tab-panel">
          {botLoading && <p className="loading">Loading bot status…</p>}
          {botError && <div className="error">Failed to load bot: {botError}</div>}
          {bot && <BotPanel bot={bot.bot_details || bot} />}
        </div>
      )}
    </div>
  )
}

function BotPanel({ bot }) {
  const phases = Object.entries(bot.StatusChanges || {})
    .filter(([, v]) => v && v.status)
    .sort((a, b) => (a[1].timestamp || 0) - (b[1].timestamp || 0))
  const agentConfig = bot.AgentConfig || {}
  const model = agentConfig.model || {}
  const agentBlock = agentConfig.agent || {}

  return (
    <div className="bot-panel">
      <h3>Bot</h3>
      <dl className="kv">
        <div className="kv-row"><dt>Bot ID</dt><dd>{bot.BotID}</dd></div>
        <div className="kv-row"><dt>Meeting link</dt><dd>{bot.MeetingLink}</dd></div>
        <div className="kv-row"><dt>Started</dt><dd>{bot.StartTime ? new Date(bot.StartTime).toLocaleString() : '—'}</dd></div>
        <div className="kv-row"><dt>Transcript ID</dt><dd>{bot.transcript_id || '—'}</dd></div>
      </dl>

      <h3>Status timeline</h3>
      {phases.length === 0 ? (
        <p className="empty">No status changes yet.</p>
      ) : (
        <ul className="timeline">
          {phases.map(([phase, v]) => (
            <li key={phase} className="timeline-item">
              <span className="tag">{phase}</span>
              <span className="text">{v.message}</span>
              {v.timestamp && (
                <span className="time">{new Date(v.timestamp * 1000).toLocaleTimeString()}</span>
              )}
            </li>
          ))}
        </ul>
      )}

      <h3>Agent</h3>
      <dl className="kv">
        <div className="kv-row"><dt>Mode</dt><dd>{agentConfig.mode || '—'}</dd></div>
        <div className="kv-row"><dt>Provider</dt><dd>{model.provider || '—'}</dd></div>
        <div className="kv-row"><dt>Voice</dt><dd>{model.voice || '—'}</dd></div>
        <div className="kv-row"><dt>Temperature</dt><dd>{model.temperature ?? '—'}</dd></div>
        <div className="kv-row"><dt>Response modality</dt><dd>{agentBlock.response_modality || '—'}</dd></div>
        <div className="kv-row"><dt>Tool results to chat</dt><dd>{String(agentBlock.tool_results_to_chat ?? '—')}</dd></div>
      </dl>
      {model.system_prompt && (
        <>
          <h3>System prompt</h3>
          <p className="prompt-text">{model.system_prompt}</p>
        </>
      )}
      {model.first_message && (
        <>
          <h3>First message</h3>
          <p className="prompt-text">{model.first_message}</p>
        </>
      )}
    </div>
  )
}
