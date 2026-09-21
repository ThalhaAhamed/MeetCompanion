"""
Agents that take part in a call by chat.

MeetStream's voice agents cannot read the meeting chat, so in "chat" and
"both" modes the server polls the chat, answers messages addressed to the
bot from the workspace, and posts the reply. These cover the mode itself,
what a launch does in each mode, and the listener's behaviour against a
scripted chat feed.
"""
import asyncio
import uuid

import pytest

from app.services import meeting_chat
from app.services.meeting_chat import MODE_BOTH, MODE_CHAT, MODE_VOICE, extract_question


@pytest.fixture(autouse=True)
def no_listener_outlives_its_test():
    yield
    meeting_chat.stop_all()


# ---------------------------------------------------------------------------
# Addressing

@pytest.mark.parametrize("text,expected", [
    ("@Meet Companion what did we decide?", "what did we decide?"),
    ("Meet Companion: who attended the kickoff", "who attended the kickoff"),
    ("/ask when is the go-live", "when is the go-live"),
    ("  /ASK   pricing?", "pricing?"),
    ("meet companion, remind me of the budget", "remind me of the budget"),
    ("what did we decide?", None),                 # not addressed to the bot
    ("@Meet Companionship is great", None),        # word boundary
    ("@Meet Companion", None),                     # nothing asked
    ("I asked Meet Companion earlier", None),      # not at the start
])
def test_only_messages_addressed_to_the_bot_are_questions(text, expected):
    assert extract_question(text, "Meet Companion") == expected


def test_bot_names_with_regex_characters_are_safe():
    assert extract_question("@Ada (v2) what's up", "Ada (v2)") == "what's up"


# ---------------------------------------------------------------------------
# The listener against a scripted chat

class FakeMeetStream:
    def __init__(self, feed):
        self.feed = list(feed)   # one get_chats result per poll
        self.sent = []
        self.polls = 0

    async def get_chats(self, bot_id, api_key=None):
        self.polls += 1
        page = self.feed[min(self.polls - 1, len(self.feed) - 1)]
        if isinstance(page, Exception):
            raise page
        return {"chatMessages": page}

    async def send_bot_message(self, bot_id, message, api_key=None):
        self.sent.append((bot_id, message))
        return {"status": "sent"}


def _msg(i, who, text):
    return {"messageId": f"m{i}", "speakerDisplayName": who, "text": text, "timestamp": "2026-09-21T10:00:00Z"}


async def _live_meeting(status="in_meeting"):
    from app.database.connection import AsyncSessionLocal
    from app.database.repositories import MeetingRepository
    from app.config import settings

    org_id = uuid.UUID(settings.DEFAULT_ORG_ID)
    async with AsyncSessionLocal() as db:
        meeting = await MeetingRepository(db).create(org_id=org_id, meeting_url="https://meet.google.com/abc", title="Live")
        await MeetingRepository(db).update_status(meeting.id, status=status)
        meeting.meetstream_bot_id = "bot-1"
        await db.commit()
        return meeting.id, org_id


@pytest.mark.asyncio
async def test_listener_answers_addressed_messages_once_and_ignores_the_rest(monkeypatch):
    meeting_id, org_id = await _live_meeting()
    history = [_msg(1, "Ada", "/ask this was typed before the bot joined")]
    fake = FakeMeetStream([
        history,                                                             # priming poll: history is not a question
        history + [_msg(2, "Ada", "hello everyone"), _msg(3, "Bob", "@Meet Companion what did we decide?")],
        history + [_msg(2, "Ada", "hello everyone"), _msg(3, "Bob", "@Meet Companion what did we decide?"),
                   _msg(4, "Meet Companion", "We decided X."),               # our own reply, echoed back
                   _msg(5, "Ada", "/ask who owns the runbook")],
    ])
    monkeypatch.setattr(meeting_chat, "POLL_SECONDS", 0.01)
    monkeypatch.setattr("app.services.meetstream.meetstream_client", fake)

    async def answer(db, org, question):
        assert org == org_id
        return f"Answer to: {question}"

    monkeypatch.setattr(meeting_chat, "answer_question", answer)

    meeting_chat.start(bot_id="bot-1", meeting_id=meeting_id, org_id=org_id, bot_name="Meet Companion", api_key_owner_id=None)
    assert meeting_chat.is_listening("bot-1")
    for _ in range(200):
        await asyncio.sleep(0.01)
        if len(fake.sent) >= 2:
            break
    meeting_chat.stop("bot-1")
    await asyncio.sleep(0.02)

    assert fake.sent == [
        ("bot-1", "Answer to: what did we decide?"),
        ("bot-1", "Answer to: who owns the runbook"),
    ]
    assert not meeting_chat.is_listening("bot-1")


@pytest.mark.asyncio
async def test_listener_stops_by_itself_when_the_meeting_ends(monkeypatch):
    meeting_id, org_id = await _live_meeting()
    fake = FakeMeetStream([[]])
    monkeypatch.setattr(meeting_chat, "POLL_SECONDS", 0.01)
    monkeypatch.setattr("app.services.meetstream.meetstream_client", fake)
    meeting_chat.start(bot_id="bot-1", meeting_id=meeting_id, org_id=org_id, bot_name="Meet Companion", api_key_owner_id=None)
    await asyncio.sleep(0.05)
    assert meeting_chat.is_listening("bot-1")

    from app.database.connection import AsyncSessionLocal
    from app.database.repositories import MeetingRepository
    async with AsyncSessionLocal() as db:
        await MeetingRepository(db).update_status(meeting_id, status="stopped")
        await db.commit()
    for _ in range(100):
        await asyncio.sleep(0.01)
        if not meeting_chat.is_listening("bot-1"):
            break
    assert not meeting_chat.is_listening("bot-1")


@pytest.mark.asyncio
async def test_listener_keeps_going_through_poll_failures(monkeypatch):
    meeting_id, org_id = await _live_meeting()
    fake = FakeMeetStream([RuntimeError("502"), [], [_msg(1, "Bob", "/ask hi")]])
    monkeypatch.setattr(meeting_chat, "POLL_SECONDS", 0.01)
    monkeypatch.setattr("app.services.meetstream.meetstream_client", fake)

    async def answer(db, org, question):
        return "ok"

    monkeypatch.setattr(meeting_chat, "answer_question", answer)
    meeting_chat.start(bot_id="bot-1", meeting_id=meeting_id, org_id=org_id, bot_name="Meet Companion", api_key_owner_id=None)
    for _ in range(200):
        await asyncio.sleep(0.01)
        if fake.sent:
            break
    meeting_chat.stop("bot-1")
    assert fake.sent == [("bot-1", "ok")]


@pytest.mark.asyncio
async def test_answer_question_never_raises(monkeypatch):
    from app.services import ask as ask_service

    async def no_provider(*a, **k):
        raise ask_service.LLMConfigError("none")

    monkeypatch.setattr(ask_service, "ask_workspace", no_provider)
    reply = await meeting_chat.answer_question(None, uuid.uuid4(), "anything")
    assert "no AI provider" in reply

    async def nothing(*a, **k):
        raise ask_service.NothingToAnswerFrom()

    monkeypatch.setattr(ask_service, "ask_workspace", nothing)
    assert "don't have any" in await meeting_chat.answer_question(None, uuid.uuid4(), "x")

    async def long(*a, **k):
        return {"answer": "word " * 500}

    monkeypatch.setattr(ask_service, "ask_workspace", long)
    assert len(await meeting_chat.answer_question(None, uuid.uuid4(), "x")) <= meeting_chat.MAX_REPLY_CHARS


# ---------------------------------------------------------------------------
# The mode, and what a launch does with it

async def _member_with_agent(authed_client, monkeypatch, agent_id="ag-1"):
    from app.database.connection import AsyncSessionLocal
    from app.database.repositories import UserRepository
    from app.services import meetstream as ms

    async def list_mia_agents(self, api_key=None):
        return {"agent_configs": [{"AgentConfigID": agent_id, "AgentName": "Ada"}]}

    async def get_mia_agent(self, agent_config_id, api_key=None):
        return {"agent_config": {"AgentConfigID": agent_config_id, "AgentName": "Ada"}}

    monkeypatch.setattr(ms.MeetStreamClient, "list_mia_agents", list_mia_agents)
    monkeypatch.setattr(ms.MeetStreamClient, "get_mia_agent", get_mia_agent)
    assert (await authed_client.put("/api/agent/api-key", json={"meetstream_api_key": "ms_test"})).status_code == 200
    async with AsyncSessionLocal() as db:
        await UserRepository(db).update_settings(authed_client.user_id, {"agent_config_ids": [agent_id], "active_agent_config_id": agent_id})
        await db.commit()


@pytest.mark.asyncio
async def test_mode_is_voice_by_default_and_owner_scoped(authed_client, monkeypatch):
    await _member_with_agent(authed_client, monkeypatch)
    agents = (await authed_client.get("/api/agent/list")).json()["agent_configs"]
    assert agents[0]["InteractionMode"] == MODE_VOICE

    r = await authed_client.put("/api/agent/mode", json={"agent_config_id": "ag-1", "mode": "telepathy"})
    assert r.status_code == 400
    r = await authed_client.put("/api/agent/mode", json={"agent_config_id": "ag-1", "mode": MODE_CHAT})
    assert r.status_code == 200, r.text
    agents = (await authed_client.get("/api/agent/list")).json()["agent_configs"]
    assert agents[0]["InteractionMode"] == MODE_CHAT
    current = (await authed_client.get("/api/agent")).json()
    assert current["InteractionMode"] == MODE_CHAT
    assert current["agent_config"]["InteractionMode"] == MODE_CHAT  # where the UI actually reads it


@pytest.mark.asyncio
@pytest.mark.parametrize("mode,voice_agent_attached,listens", [
    (MODE_VOICE, True, False),
    (MODE_CHAT, False, True),
    (MODE_BOTH, True, True),
])
async def test_launch_honours_the_mode(authed_client, monkeypatch, mode, voice_agent_attached, listens):
    await _member_with_agent(authed_client, monkeypatch)
    assert (await authed_client.put("/api/agent/mode", json={"agent_config_id": "ag-1", "mode": mode})).status_code == 200

    from app.api import meetings as meetings_api
    created = {}

    async def create_bot(**kwargs):
        created.update(kwargs)
        return {"bot_id": "bot-launch", "transcript_id": "tr-1"}

    started = {}
    monkeypatch.setattr(meetings_api.meetstream_client, "create_bot", create_bot)
    monkeypatch.setattr(meeting_chat, "start", lambda **kw: started.update(kw))

    r = await authed_client.post("/api/meetings", json={"meeting_url": "https://meet.google.com/abc-defg-hij", "title": "Sync"})
    assert r.status_code == 201, r.text
    assert (created["agent_config_id"] == "ag-1") is voice_agent_attached
    assert bool(started) is listens
    if listens:
        assert started["bot_id"] == "bot-launch" and started["bot_name"] == "Ada"
    # The mode travels with the meeting so a restart can resume the listener.
    detail = (await authed_client.get(f"/api/meetings/{r.json()['id']}")).json()
    assert detail["custom_attributes"]["interaction_mode"] == mode
    # The join message tells people how to ask, when the chat is listening.
    assert ('"/ask"' in created["bot_message"]) is listens
    # Undo any real client patching between parametrised runs.
    monkeypatch.undo()


@pytest.mark.asyncio
async def test_terminal_webhooks_stop_the_listener(authed_client, monkeypatch):
    stopped = []
    monkeypatch.setattr(meeting_chat, "stop", lambda bot_id: stopped.append(bot_id))
    from app.api import webhooks as webhooks_api
    from app.database.connection import AsyncSessionLocal
    from app.database.repositories import MeetingRepository
    from app.config import settings

    monkeypatch.setattr(webhooks_api, "effective_webhook_secret", lambda: None)
    # Unsigned events are only honoured for bots we launched.
    async with AsyncSessionLocal() as db:
        for event in ("bot.stopped", "bot.failed", "bot.done"):
            m = await MeetingRepository(db).create(org_id=uuid.UUID(settings.DEFAULT_ORG_ID), meeting_url="https://meet.google.com/x", title=event)
            m.meetstream_bot_id = f"b-{event}"
        await db.commit()
    for i, event in enumerate(("bot.stopped", "bot.failed", "bot.done")):
        r = await authed_client.post("/api/webhooks/meetstream", json={"event": event, "bot_id": f"b-{event}", "timestamp": f"2026-09-21T10:00:0{i}Z"})
        assert r.status_code in (200, 202), r.text
    await asyncio.sleep(0.2)
    assert {"b-bot.stopped", "b-bot.failed", "b-bot.done"} <= set(stopped)
