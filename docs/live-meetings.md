# Live meetings: reaching your server

Notes, search, Ask AI and transcript upload work entirely on your machine.
**Sending a bot into a live call needs MeetStream to reach your server** for two
things: webhook deliveries (`/api/webhooks/meetstream`) and the voice agent's
tool calls (`/mcp`).

This has nothing to do with which database you use — SQLite or your own
Postgres only changes where data is stored. It is about where the *server*
runs: on a host with a public address (a VPS, Railway, Fly, …) no tunnel is
needed at all; on a laptop, some tunnel is unavoidable while a bot is in a
call.

1. Expose the server on a public URL — a real domain behind HTTPS, or during
   development a tunnel such as `cloudflared tunnel --url http://localhost:8000`
   or `ngrok http 8000`. Cloudflare's free *quick* tunnels
   (`*.trycloudflare.com`) work for webhooks, `/mcp` and updating an existing
   agent, but MeetStream's agent-*creation* endpoint returns a 500 when a
   `custom_functions` URL is on that domain — so create the agent while on
   another host, or use a named Cloudflare tunnel / ngrok. Quick-tunnel URLs
   also change on every launch; for anything beyond a one-off test use a
   fixed domain.
2. Set `MCP_SERVER_URL` to `https://<that-host>/mcp` (in `.env` or the
   environment) and restart. The webhook callback URL is derived from it.
3. Add your MeetStream API key in **Settings → Meetings** and a webhook
   signing secret (the same value on both sides).
4. Create or activate an agent in **Agent**; Meet Companion wires the MCP
   server URL, the `share_in_chat` chat relay and your workspace's token
   into it. **Re-activate the agent whenever the URL changes** — that is
   what re-points its wiring at the new host.

Without a reachable URL a bot still joins and records, and **Stop** and
**Reprocess** still work (the transcript is fetched by id), but nothing
happens automatically after the call and the voice agent cannot reach
memory. A call in which nobody speaks produces no transcript on
MeetStream's side; the meeting is marked failed with that reason.

## Voice, chat, or both

On the **Agent** page each agent has an *In the call* setting:

| Mode | In the call |
| --- | --- |
| **Voice** (default) | MeetStream's voice agent joins and answers when spoken to by name. |
| **Chat** | No voice agent. The bot joins silently; questions typed in the meeting chat are answered in the chat. |
| **Voice and chat** | Both. |

To ask in the chat, start a message with the agent's name or `/ask`, e.g.
`@Meet Companion what did we decide about pricing?` or `/ask who owns the
runbook`. The bot's welcome message says so when it joins. Answers come from
the same retrieval as **Ask AI** - notes, meetings and uploaded documents of
the workspace - using the workspace's AI provider, kept to a few plain
sentences.

How it works, and why it differs from voice: MeetStream's agents hear the
room but never read the chat panel, and no webhook carries chat messages.
So in a chat mode Meet Companion's server polls the bot's chat every few
seconds while the call is live, picks out messages addressed to the bot,
and posts the reply through the bot. That needs the server running for the
whole call - on the desktop app, the app that launched the bot stays open.
Chat answers do not need `MCP_SERVER_URL`; only the voice agent's tool
calls do.
