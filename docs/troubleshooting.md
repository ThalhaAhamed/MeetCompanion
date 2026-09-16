# Troubleshooting

**A meeting sits at "Extracting…" / "joining" forever.** MeetStream cannot
reach your server: its webhooks never arrive. Check `MCP_SERVER_URL` is a
public URL (see [Live meetings](live-meetings.md)), that
the tunnel is still running, and re-activate the agent after changing it.
*Reprocess* on the meeting fetches the transcript by id without webhooks.

**"Processed without AI (…)"** on a meeting. The AI provider failed and the
rule-based parser ran instead; the message in brackets is the provider's own
reason. For Ollama, `Model 'x' is not pulled` means `ollama pull x`; a CUDA
*out of memory* means the GPU is full - close other GPU work or pick a
smaller model. Fix the provider in Settings, then *Reprocess*.

**Ask AI answers "Could not answer that".** Same cause as above; the error
text is the provider's. *Test connection* in Settings → AI provider reproduces
it without a meeting.

**Blank page after upgrading from v0.2.0.** Fixed in v0.3.1 - accounts from
before workspaces had no membership row. Upgrade; the server repairs it on
start.

**Port 8000 already in use.** Find what holds it (`netstat -ano | findstr :8000`
on Windows, `lsof -i :8000` elsewhere) and stop it - the Vite dev proxy in
`frontend/vite.config.js` expects the API on 8000. Running the API alone on
another port is `scripts/dev.py --port 8010 --no-ui`.

**Database "Not reachable" in Settings.** The banner shows the driver's
reason. *Connection refused* → nothing listening on that host/port;
*could not resolve host* → check the hostname; a Supabase direct URL on a
network without IPv6 → use the pooler connection string instead.

**The desktop app shows the sign-in screen although it used to sign itself in.**
That happens only when the workspace has more than one owner - the device key
signs in *the* owner and refuses to guess between several. Sign in normally.

**"Incorrect email or password" right after switching databases.** Accounts
live in the database, so on a database that already has people in it your
old account does not exist — sign in with an account from *that* database,
or ask its owner to add you. On an *empty* database (a fresh Postgres) your
account is carried over automatically as of v0.4.3 and you stay signed in;
your meetings and notes are not copied — they remain in the previous
database. To bring them across, see `scripts/import_from_postgres.py`.
