"""Smoke tests verifying the test harness and basic app health."""

from __future__ import annotations


async def test_health(client):
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_list_works_empty(client):
    resp = await client.get("/api/works/")
    assert resp.status_code == 200
    assert resp.json() == []
