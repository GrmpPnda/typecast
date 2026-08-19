"""Tests for series CRUD."""

from __future__ import annotations

import uuid


async def test_create_and_list_series(client):
    resp = await client.post("/api/series/", json={"title": "The Saga"})
    assert resp.status_code == 201, resp.text
    series = resp.json()
    assert series["title"] == "The Saga"

    resp = await client.get("/api/series/")
    assert resp.status_code == 200
    assert any(s["id"] == series["id"] for s in resp.json())


async def test_update_series(client):
    series = (await client.post("/api/series/", json={"title": "S"})).json()
    resp = await client.patch(f"/api/series/{series['id']}", json={"title": "Renamed Saga"})
    assert resp.status_code == 200
    assert resp.json()["title"] == "Renamed Saga"


async def test_delete_series(client):
    series = (await client.post("/api/series/", json={"title": "S"})).json()
    resp = await client.delete(f"/api/series/{series['id']}")
    assert resp.status_code == 204
    resp = await client.get(f"/api/series/{series['id']}")
    assert resp.status_code == 404


async def test_get_missing_series_404(client):
    resp = await client.get(f"/api/series/{uuid.uuid4()}")
    assert resp.status_code == 404
