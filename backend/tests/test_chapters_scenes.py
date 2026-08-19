"""Tests for chapter and scene CRUD, ordering, and split."""

from __future__ import annotations

import pytest_asyncio


@pytest_asyncio.fixture
async def work(client):
    resp = await client.post("/api/works/", json={"title": "Book", "author": "Auth"})
    return resp.json()


async def _create_chapter(client, work_id, title="Chapter 1", **extra):
    resp = await client.post(f"/api/{work_id}/chapters", json={"title": title, **extra})
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_create_chapter(client, work):
    ch = await _create_chapter(client, work["id"], title="Opening")
    assert ch["title"] == "Opening"

    resp = await client.get(f"/api/{work['id']}/chapters")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


async def test_update_and_delete_chapter(client, work):
    ch = await _create_chapter(client, work["id"])
    resp = await client.put(f"/api/chapters/{ch['id']}", json={"title": "New Title"})
    assert resp.status_code == 200
    assert resp.json()["title"] == "New Title"

    resp = await client.delete(f"/api/chapters/{ch['id']}")
    assert resp.status_code == 204


async def test_create_scene_in_chapter(client, work):
    ch = await _create_chapter(client, work["id"])
    resp = await client.post(
        f"/api/chapters/{ch['id']}/scenes",
        json={"content": "It was a dark and stormy night.", "sort_order": 0},
    )
    assert resp.status_code == 201, resp.text
    scene = resp.json()
    assert "dark and stormy" in scene["content"]

    resp = await client.get(f"/api/chapters/{ch['id']}/scenes")
    assert len(resp.json()) == 1


async def test_update_scene(client, work):
    ch = await _create_chapter(client, work["id"])
    scene = (await client.post(
        f"/api/chapters/{ch['id']}/scenes", json={"content": "Draft"}
    )).json()
    resp = await client.put(f"/api/scenes/{scene['id']}", json={"content": "Revised"})
    assert resp.status_code == 200
    assert resp.json()["content"] == "Revised"


async def test_scene_split(client, work):
    ch = await _create_chapter(client, work["id"])
    scene = (await client.post(
        f"/api/chapters/{ch['id']}/scenes",
        json={"content": "First part\n---\nSecond part"},
    )).json()
    resp = await client.post(f"/api/scenes/{scene['id']}/split")
    assert resp.status_code == 200, resp.text
    scenes = resp.json()
    assert len(scenes) >= 2
