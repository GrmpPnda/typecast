"""Tests for work CRUD and user-scoped ownership."""

from __future__ import annotations


async def _create_work(client, title="My Novel", author="A. Writer", **extra):
    payload = {"title": title, "author": author, **extra}
    resp = await client.post("/api/works/", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_create_and_get_work(client):
    work = await _create_work(client, title="Test Book")
    assert work["title"] == "Test Book"
    assert work["author"] == "A. Writer"

    resp = await client.get(f"/api/works/{work['id']}")
    assert resp.status_code == 200
    assert resp.json()["id"] == work["id"]


async def test_list_works_returns_created(client):
    await _create_work(client, title="One")
    await _create_work(client, title="Two")
    resp = await client.get("/api/works/")
    assert resp.status_code == 200
    titles = {w["title"] for w in resp.json()}
    assert {"One", "Two"} <= titles


async def test_update_work(client):
    work = await _create_work(client)
    resp = await client.put(f"/api/works/{work['id']}", json={"title": "Renamed"})
    assert resp.status_code == 200
    assert resp.json()["title"] == "Renamed"


async def test_delete_work(client):
    work = await _create_work(client)
    resp = await client.delete(f"/api/works/{work['id']}")
    assert resp.status_code == 204

    resp = await client.get(f"/api/works/{work['id']}")
    assert resp.status_code == 404


async def test_get_missing_work_404(client):
    import uuid

    resp = await client.get(f"/api/works/{uuid.uuid4()}")
    assert resp.status_code == 404


async def test_created_work_is_owned_by_user(client, test_user):
    """A newly created work should be assigned to the authenticated user."""
    work = await _create_work(client)
    # It shows up in the user-scoped listing.
    resp = await client.get("/api/works/")
    ids = {w["id"] for w in resp.json()}
    assert work["id"] in ids
