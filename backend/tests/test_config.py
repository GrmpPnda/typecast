"""Tests for app config get/update with secret masking."""

from __future__ import annotations


async def test_list_config_returns_known_keys(client):
    resp = await client.get("/api/config/")
    assert resp.status_code == 200
    entries = resp.json()
    assert isinstance(entries, list)
    keys = {e["key"] for e in entries}
    # A few well-known config keys should always be present.
    assert "ai_provider" in keys


async def test_update_config_roundtrip(client):
    resp = await client.put(
        "/api/config/",
        json={"entries": [{"key": "ai_provider", "value": "openai"}]},
    )
    assert resp.status_code == 200
    entries = {e["key"]: e["value"] for e in resp.json()}
    assert entries["ai_provider"] == "openai"


async def test_secret_is_masked(client):
    """Secret keys should be returned masked, not in plaintext."""
    await client.put(
        "/api/config/",
        json={"entries": [{"key": "anthropic_api_key", "value": "sk-secret-123456"}]},
    )
    resp = await client.get("/api/config/")
    entry = next((e for e in resp.json() if e["key"] == "anthropic_api_key"), None)
    assert entry is not None
    assert entry["is_secret"] is True
    assert "sk-secret-123456" not in (entry["value"] or "")
