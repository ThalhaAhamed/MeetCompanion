"""
Tests for the notebook: folders, notes, filtering and Ask AI.

The folder-tree cases matter most - they are where a bug silently loses a
user's notes or detaches a whole branch from the tree.
"""
import pytest


async def _create_folder(client, name, parent_id=None):
    response = await client.post(
        "/api/notebook/folders", json={"name": name, "parent_id": parent_id}
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _create_note(client, title, content="", **extra):
    payload = {"title": title, "content": content, **extra}
    response = await client.post("/api/notebook/notes", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


# --------------------------------------------------------------------------
# Access control
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_notebook_requires_a_session(client):
    assert (await client.get("/api/notebook/notes")).status_code == 401


# --------------------------------------------------------------------------
# Notes CRUD
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_note_lifecycle(authed_client):
    note = await _create_note(authed_client, "Sprint planning", "We agreed to ship Friday.")
    note_id = note["id"]
    assert note["title"] == "Sprint planning"

    fetched = await authed_client.get(f"/api/notebook/notes/{note_id}")
    assert fetched.json()["content"] == "We agreed to ship Friday."

    renamed = await authed_client.patch(
        f"/api/notebook/notes/{note_id}", json={"title": "Sprint planning (final)"}
    )
    assert renamed.json()["title"] == "Sprint planning (final)"

    deleted = await authed_client.delete(f"/api/notebook/notes/{note_id}")
    assert deleted.status_code == 200
    assert (await authed_client.get(f"/api/notebook/notes/{note_id}")).status_code == 404


@pytest.mark.asyncio
async def test_missing_note_returns_404(authed_client):
    missing = "11111111-2222-3333-4444-555555555555"
    assert (await authed_client.get(f"/api/notebook/notes/{missing}")).status_code == 404


@pytest.mark.asyncio
async def test_listing_omits_full_content_but_gives_an_excerpt(authed_client):
    await _create_note(authed_client, "Long", "x" * 500)

    body = (await authed_client.get("/api/notebook/notes")).json()
    row = body["notes"][0]
    assert "content" not in row
    assert len(row["excerpt"]) <= 240


@pytest.mark.asyncio
async def test_favorite_toggle_and_filter(authed_client):
    plain = await _create_note(authed_client, "Plain")
    starred = await _create_note(authed_client, "Starred")
    await authed_client.patch(f"/api/notebook/notes/{starred['id']}", json={"is_favorite": True})

    body = (await authed_client.get("/api/notebook/notes?favorites_only=true")).json()
    titles = [n["title"] for n in body["notes"]]
    assert titles == ["Starred"]
    assert plain["is_favorite"] is False


# --------------------------------------------------------------------------
# Search, filter, sort
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_matches_title_and_body(authed_client):
    await _create_note(authed_client, "Pricing decision", "forty dollars per seat")
    await _create_note(authed_client, "Unrelated", "nothing to see")

    by_title = (await authed_client.get("/api/notebook/notes?q=pricing")).json()
    assert [n["title"] for n in by_title["notes"]] == ["Pricing decision"]

    by_body = (await authed_client.get("/api/notebook/notes?q=seat")).json()
    assert [n["title"] for n in by_body["notes"]] == ["Pricing decision"]


@pytest.mark.asyncio
async def test_filter_by_tag_and_type(authed_client):
    await _create_note(authed_client, "Tagged", tags=["alpha"], note_type="research")
    await _create_note(authed_client, "Untagged", tags=["beta"])

    tagged = (await authed_client.get("/api/notebook/notes?tag=alpha")).json()
    assert [n["title"] for n in tagged["notes"]] == ["Tagged"]

    typed = (await authed_client.get("/api/notebook/notes?note_type=research")).json()
    assert [n["title"] for n in typed["notes"]] == ["Tagged"]

    tags = (await authed_client.get("/api/notebook/tags")).json()["tags"]
    assert set(tags) == {"alpha", "beta"}


@pytest.mark.asyncio
async def test_sort_by_title(authed_client):
    await _create_note(authed_client, "Beta")
    await _create_note(authed_client, "Alpha")

    body = (await authed_client.get("/api/notebook/notes?sort=title&descending=false")).json()
    assert [n["title"] for n in body["notes"]] == ["Alpha", "Beta"]


@pytest.mark.asyncio
async def test_pagination_reports_total(authed_client):
    for index in range(5):
        await _create_note(authed_client, f"Note {index}")

    body = (await authed_client.get("/api/notebook/notes?limit=2")).json()
    assert body["total"] == 5
    assert len(body["notes"]) == 2


# --------------------------------------------------------------------------
# Folders
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_folder_tree_nests_and_counts_notes(authed_client):
    work = await _create_folder(authed_client, "Work")
    alpha = await _create_folder(authed_client, "Project Alpha", parent_id=work)
    await _create_note(authed_client, "Kickoff", folder_id=alpha)

    body = (await authed_client.get("/api/notebook/folders")).json()
    assert [f["name"] for f in body["folders"]] == ["Work"]

    child = body["folders"][0]["children"][0]
    assert child["name"] == "Project Alpha"
    assert child["note_count"] == 1
    assert body["counts"]["total"] == 1


@pytest.mark.asyncio
async def test_notes_can_be_moved_between_folders(authed_client):
    source = await _create_folder(authed_client, "Source")
    target = await _create_folder(authed_client, "Target")
    note = await _create_note(authed_client, "Movable", folder_id=source)

    moved = await authed_client.patch(
        f"/api/notebook/notes/{note['id']}", json={"folder_id": target}
    )
    assert moved.json()["folder_id"] == target

    in_target = (await authed_client.get(f"/api/notebook/notes?folder_id={target}")).json()
    assert [n["title"] for n in in_target["notes"]] == ["Movable"]


@pytest.mark.asyncio
async def test_note_can_be_moved_back_to_the_root(authed_client):
    folder = await _create_folder(authed_client, "Somewhere")
    note = await _create_note(authed_client, "Filed", folder_id=folder)

    moved = await authed_client.patch(
        f"/api/notebook/notes/{note['id']}", json={"move_to_root": True}
    )
    assert moved.json()["folder_id"] is None

    unfiled = (await authed_client.get("/api/notebook/notes?unfiled=true")).json()
    assert [n["title"] for n in unfiled["notes"]] == ["Filed"]


@pytest.mark.asyncio
async def test_deleting_a_folder_keeps_its_notes_by_default(authed_client):
    """Deleting a folder must not silently destroy the notes inside it."""
    parent = await _create_folder(authed_client, "Parent")
    child = await _create_folder(authed_client, "Child", parent_id=parent)
    await _create_note(authed_client, "Survivor", folder_id=child)

    assert (await authed_client.delete(f"/api/notebook/folders/{child}")).status_code == 200

    remaining = (await authed_client.get("/api/notebook/notes")).json()
    assert [n["title"] for n in remaining["notes"]] == ["Survivor"]
    assert remaining["notes"][0]["folder_id"] == parent


@pytest.mark.asyncio
async def test_cascade_delete_removes_the_whole_subtree(authed_client):
    parent = await _create_folder(authed_client, "Parent")
    child = await _create_folder(authed_client, "Child", parent_id=parent)
    await _create_note(authed_client, "Doomed", folder_id=child)

    response = await authed_client.delete(f"/api/notebook/folders/{parent}?cascade=true")
    assert response.status_code == 200

    assert (await authed_client.get("/api/notebook/notes")).json()["total"] == 0
    assert (await authed_client.get("/api/notebook/folders")).json()["folders"] == []


@pytest.mark.asyncio
async def test_folder_cannot_be_moved_inside_its_own_descendant(authed_client):
    """This would detach the branch from the root and strand every note in it."""
    parent = await _create_folder(authed_client, "Parent")
    child = await _create_folder(authed_client, "Child", parent_id=parent)

    response = await authed_client.patch(
        f"/api/notebook/folders/{parent}", json={"parent_id": child}
    )
    assert response.status_code == 400
    assert "inside itself" in response.json()["detail"]


@pytest.mark.asyncio
async def test_folder_cannot_be_its_own_parent(authed_client):
    folder = await _create_folder(authed_client, "Solo")
    response = await authed_client.patch(
        f"/api/notebook/folders/{folder}", json={"parent_id": folder}
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_creating_in_a_missing_folder_is_rejected(authed_client):
    missing = "11111111-2222-3333-4444-555555555555"
    response = await authed_client.post(
        "/api/notebook/notes", json={"title": "Orphan", "folder_id": missing}
    )
    assert response.status_code == 404


# --------------------------------------------------------------------------
# Ask AI
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ask_requires_a_configured_provider(authed_client, monkeypatch, tmp_path):
    monkeypatch.setenv("MEET_COMPANION_CONFIG", str(tmp_path / "empty.json"))
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.delenv("LLM_API_KEY", raising=False)

    # Also clear the legacy fallbacks, otherwise a key in the developer's own
    # .env would satisfy the provider and this would test nothing.
    from app.config import settings as app_settings

    monkeypatch.setattr(app_settings, "LLM_API_KEY", None, raising=False)
    monkeypatch.setattr(app_settings, "OPENAI_API_KEY", None, raising=False)

    from app.runtime_config import reset_config

    reset_config()

    await _create_note(authed_client, "Anything", "content")
    response = await authed_client.post("/api/notebook/ask", json={"question": "What?"})

    assert response.status_code == 400
    assert "Settings" in response.json()["detail"]


@pytest.mark.asyncio
async def test_ask_grounds_the_answer_in_selected_notes(
    authed_client, monkeypatch, tmp_path, httpx_mock
):
    monkeypatch.setenv("MEET_COMPANION_CONFIG", str(tmp_path / "cfg.json"))
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("LLM_MODEL", "llama3.1")

    from app.runtime_config import reset_config

    reset_config()

    note = await _create_note(
        authed_client, "Pricing", "We agreed on forty dollars per seat."
    )
    httpx_mock.add_response(
        url="http://localhost:11434/api/chat",
        json={"message": {"content": "Forty dollars per seat."}},
    )

    response = await authed_client.post(
        "/api/notebook/ask",
        json={"question": "What did we agree on?", "note_ids": [note["id"]]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "Forty dollars per seat."
    assert [s["title"] for s in body["sources"]] == ["Pricing"]

    import json as _json

    sent = _json.loads(httpx_mock.get_requests()[0].content)
    # The note text must actually reach the model, or the answer is ungrounded.
    assert "forty dollars per seat" in sent["messages"][1]["content"]


@pytest.mark.asyncio
async def test_ask_with_no_notes_in_scope_says_so(
    authed_client, monkeypatch, tmp_path
):
    monkeypatch.setenv("MEET_COMPANION_CONFIG", str(tmp_path / "cfg.json"))
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("LLM_MODEL", "llama3.1")

    from app.runtime_config import reset_config

    reset_config()

    response = await authed_client.post("/api/notebook/ask", json={"question": "Anything?"})
    assert response.status_code == 200
    assert "no notes in scope" in response.json()["answer"]
