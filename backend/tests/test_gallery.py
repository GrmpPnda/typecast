"""Tests for the unified image gallery: aggregation, update, reassign, bulk delete."""

from __future__ import annotations

import uuid

import pytest_asyncio

from app.models.image import Image


@pytest_asyncio.fixture
async def work(client):
    resp = await client.post("/api/works/", json={"title": "Gallery Book", "author": "A"})
    return resp.json()


@pytest_asyncio.fixture
async def second_work(client):
    resp = await client.post("/api/works/", json={"title": "Other Book", "author": "A"})
    return resp.json()


async def _add_image(session_factory, work_id, name="pic.png", tags="", alt=""):
    """Insert an Image row directly (upload path writes files; gallery only needs the row)."""
    image_id = uuid.uuid4()
    async with session_factory() as session:
        img = Image(
            id=image_id,
            work_id=uuid.UUID(work_id),
            filename=f"{image_id}.png",
            original_name=name,
            mime_type="image/png",
            size_bytes=1234,
            width=100,
            height=100,
            alt_text=alt,
            tags=tags,
        )
        session.add(img)
        await session.commit()
    return str(image_id)


async def test_empty_gallery(client):
    resp = await client.get("/api/gallery")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_gallery_includes_work_cover(client, work, session_factory):
    await client.put(f"/api/works/{work['id']}", json={"cover_image_path": "/uploads/covers/x.png"})
    resp = await client.get("/api/gallery")
    assert resp.status_code == 200
    sources = {item["source"] for item in resp.json()}
    assert "cover" in sources
    cover = next(i for i in resp.json() if i["source"] == "cover")
    assert cover["manageable"] is False
    assert cover["work_id"] == work["id"]


async def test_gallery_includes_gallery_image(client, work, session_factory):
    img_id = await _add_image(session_factory, work["id"], name="scene.png", tags="hero")
    resp = await client.get("/api/gallery")
    items = resp.json()
    gallery_items = [i for i in items if i["source"] == "gallery"]
    assert len(gallery_items) == 1
    item = gallery_items[0]
    assert item["id"] == f"image:{img_id}"
    assert item["manageable"] is True
    assert item["tags"] == "hero"
    assert item["work_title"] == "Gallery Book"


async def test_update_gallery_image_alt_and_tags(client, work, session_factory):
    img_id = await _add_image(session_factory, work["id"])
    resp = await client.put(
        f"/api/gallery/images/{img_id}",
        json={"alt_text": "A hero shot", "tags": "hero,cover"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["alt_text"] == "A hero shot"
    assert body["tags"] == "hero,cover"


async def test_reassign_image_to_another_work(client, work, second_work, session_factory):
    img_id = await _add_image(session_factory, work["id"])
    resp = await client.put(
        f"/api/gallery/images/{img_id}/reassign",
        json={"work_id": second_work["id"]},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["work_id"] == second_work["id"]
    assert resp.json()["work_title"] == "Other Book"


async def test_reassign_to_same_work_rejected(client, work, session_factory):
    img_id = await _add_image(session_factory, work["id"])
    resp = await client.put(
        f"/api/gallery/images/{img_id}/reassign",
        json={"work_id": work["id"]},
    )
    assert resp.status_code == 400


async def test_bulk_delete(client, work, session_factory):
    a = await _add_image(session_factory, work["id"], name="a.png")
    b = await _add_image(session_factory, work["id"], name="b.png")
    resp = await client.post("/api/gallery/images/bulk-delete", json={"image_ids": [a, b]})
    assert resp.status_code == 204

    resp = await client.get("/api/gallery")
    gallery_items = [i for i in resp.json() if i["source"] == "gallery"]
    assert gallery_items == []


async def test_update_missing_image_404(client):
    resp = await client.put(
        f"/api/gallery/images/{uuid.uuid4()}",
        json={"alt_text": "x"},
    )
    assert resp.status_code == 404
