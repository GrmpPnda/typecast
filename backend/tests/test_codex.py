"""Tests for codex entry CRUD and work association."""

from __future__ import annotations

import pytest_asyncio


@pytest_asyncio.fixture
async def work(client):
    resp = await client.post("/api/works/", json={"title": "Codex Book", "author": "A"})
    return resp.json()


async def test_create_codex_entry(client, work):
    resp = await client.post(
        "/api/codex/",
        json={
            "entry_type": "character",
            "name": "Aria",
            "description": "The protagonist",
            "work_ids": [work["id"]],
        },
    )
    assert resp.status_code == 201, resp.text
    entry = resp.json()
    assert entry["name"] == "Aria"
    assert entry["entry_type"] == "character"
    assert work["id"] in entry["work_ids"]


async def test_list_codex_filtered_by_work(client, work):
    await client.post("/api/codex/", json={
        "entry_type": "location", "name": "The Keep", "work_ids": [work["id"]],
    })
    resp = await client.get(f"/api/codex/?work_id={work['id']}")
    assert resp.status_code == 200
    names = {e["name"] for e in resp.json()}
    assert "The Keep" in names


async def test_update_codex_entry(client, work):
    entry = (await client.post("/api/codex/", json={
        "entry_type": "character", "name": "Bob", "work_ids": [work["id"]],
    })).json()
    resp = await client.patch(f"/api/codex/{entry['id']}", json={"name": "Robert"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Robert"


async def test_delete_codex_entry(client, work):
    entry = (await client.post("/api/codex/", json={
        "entry_type": "item", "name": "Sword", "work_ids": [work["id"]],
    })).json()
    resp = await client.delete(f"/api/codex/{entry['id']}")
    assert resp.status_code == 204
