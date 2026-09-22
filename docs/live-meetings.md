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

Without a reachable URL a bot still joins and records, and the meeting still
follows it: the server asks MeetStream for the bot's state every 20 seconds
while a call is live (Joining → In the call → Recording → Left the call), and
once MeetStream has finished the transcript it fetches it and runs the
summary, memory and action-item extraction by itself — the webhooks are the
faster path, not the only one. What a tunnel-less install does lose is the
agent: it cannot reach memory during the call. A call in which nobody speaks
produces no transcript on MeetStream's side; the meeting is marked failed
with that reason.

## Answering by voice or in the chat

On the **Agent** page each agent has a *How it answers in a call* setting:

| Mode | In the call |
| --- | --- |
| **Voice** (default) | The agent answers out loud when someone says its name. |
| **Chat** | The agent stays silent; when someone says its name, the answer is posted in the meeting chat. |

In both modes the agent hears the room and is addressed by name — "Ada,
what did we decide last time?" — and answers from the workspace through the
MCP server as before. The setting is MeetStream's `response_modality` on the
agent (`audio` or `chat`), so it applies to every call that agent joins, from
any install.

**Questions typed into the meeting chat cannot be answered.** MeetStream's
agents do not read the chat panel, no webhook carries chat messages, and the
`get_chats` endpoint only returns the chat after the call has ended (verified
against a live meeting). If MeetStream adds a live chat feed, a typed mode
becomes possible; until then, ask by voice.
