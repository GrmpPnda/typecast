from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_db
from app.models.config import AppConfig
from app.schemas.config import ConfigBulkUpdate, ConfigEntryResponse
from app.services.crypto import decrypt, encrypt

logger = logging.getLogger(__name__)

router = APIRouter()

KNOWN_KEYS = {
    "ai_provider": {"is_secret": False, "default": "anthropic"},
    "anthropic_api_key": {"is_secret": True, "default": ""},
    "openai_api_key": {"is_secret": True, "default": ""},
    "anthropic_model": {"is_secret": False, "default": "claude-sonnet-4-6"},
    "openai_model": {"is_secret": False, "default": "gpt-4o"},
    "bedrock_enabled": {"is_secret": False, "default": "false"},
    "bedrock_region": {"is_secret": False, "default": "us-east-1"},
    "bedrock_model_id": {"is_secret": False, "default": "us.anthropic.claude-sonnet-4-6"},
    "bedrock_aws_profile": {"is_secret": False, "default": ""},
    "image_provider": {"is_secret": False, "default": ""},
    "image_model": {"is_secret": False, "default": ""},
    "bedrock_image_region": {"is_secret": False, "default": ""},
    "spellcheck_enabled": {"is_secret": False, "default": "true"},
    "polly_enabled": {"is_secret": False, "default": "false"},
    "polly_region": {"is_secret": False, "default": "us-east-1"},
    "polly_narrator_voice": {"is_secret": False, "default": "Ruth"},
    "polly_engine": {"is_secret": False, "default": "long-form"},
    "polly_aws_profile": {"is_secret": False, "default": "default"},
    "gdrive_enabled": {"is_secret": False, "default": "false"},
    "gdrive_client_id": {"is_secret": False, "default": ""},
    "gdrive_client_secret": {"is_secret": True, "default": ""},
    "gdrive_refresh_token": {"is_secret": True, "default": ""},
    "gdrive_folder_id": {"is_secret": False, "default": ""},
}


def _mask(value: str) -> str:
    if not value or len(value) < 8:
        return "*" * len(value) if value else ""
    return value[:4] + "*" * (len(value) - 8) + value[-4:]


@router.get("/", response_model=list[ConfigEntryResponse])
async def list_config(db: AsyncSession = Depends(get_db)):
    logger.debug("Listing config (%d known keys)", len(KNOWN_KEYS))
    result = await db.execute(select(AppConfig))
    rows = {r.key: r for r in result.scalars().all()}

    entries = []
    for key, meta in KNOWN_KEYS.items():
        row = rows.get(key)
        if row:
            raw = decrypt(row.value) if row.is_secret and row.value else row.value
            display = _mask(raw) if row.is_secret else raw
        else:
            raw = meta["default"]
            display = _mask(raw) if meta["is_secret"] else raw
        entries.append(ConfigEntryResponse(
            key=key,
            value=display,
            is_secret=meta["is_secret"],
        ))
    return entries


@router.put("/", response_model=list[ConfigEntryResponse])
async def update_config(
    data: ConfigBulkUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(AppConfig))
    existing = {r.key: r for r in result.scalars().all()}

    logger.info("Updating %d config entr(ies)", len(data.entries))
    for entry in data.entries:
        if entry.key not in KNOWN_KEYS:
            logger.warning("Ignoring unknown config key: %s", entry.key)
            continue
        meta = KNOWN_KEYS[entry.key]
        is_secret = meta["is_secret"]

        if is_secret and entry.value and "*" in entry.value:
            logger.debug("Skipping masked secret for key %s", entry.key)
            continue

        store_value = encrypt(entry.value) if is_secret and entry.value else entry.value

        if entry.key in existing:
            existing[entry.key].value = store_value
            existing[entry.key].is_secret = is_secret
        else:
            row = AppConfig(key=entry.key, value=store_value, is_secret=is_secret)
            db.add(row)

    await db.commit()
    return await list_config(db)


async def set_config_value(db: AsyncSession, key: str, value: str) -> None:
    """Write a single config value, encrypting it when the key is a secret.

    Used by flows that obtain a value server-side rather than from user input —
    the OAuth callback storing a refresh token, for example. The bulk update
    endpoint skips secrets containing ``*`` so masked values aren't written back,
    which makes it unsuitable for that.
    """
    meta = KNOWN_KEYS.get(key)
    if meta is None:
        raise ValueError(f"Unknown config key: {key}")

    is_secret = meta["is_secret"]
    store_value = encrypt(value) if is_secret and value else value

    result = await db.execute(select(AppConfig).where(AppConfig.key == key))
    row = result.scalar_one_or_none()
    if row is None:
        db.add(AppConfig(key=key, value=store_value, is_secret=is_secret))
    else:
        row.value = store_value
        row.is_secret = is_secret

    await db.commit()
    logger.info("Config key %s updated (secret=%s)", key, is_secret)


async def get_config_value(db: AsyncSession, key: str) -> str:
    result = await db.execute(select(AppConfig).where(AppConfig.key == key))
    row = result.scalar_one_or_none()
    if row is None:
        return KNOWN_KEYS.get(key, {}).get("default", "")
    if row.is_secret and row.value:
        return decrypt(row.value)
    return row.value


_TEXT_MODEL_KEYWORDS = {
    "claude", "nova-pro", "nova-lite", "nova-micro",
    "nova-premier", "llama", "mistral", "deepseek",
}
_IMAGE_MODEL_KEYWORDS = {
    "nova-canvas", "stable", "titan-image", "nova-reel",
}
_EXCLUDE_KEYWORDS = {
    "embed", "image", "stable", "cohere", "titan",
    "twelvelabs", "pegasus", "upscale",
}


def _paginate_inference_profiles(client) -> list[dict]:
    """Paginate through all Bedrock inference profiles."""
    profiles: list[dict] = []
    kwargs = {"maxResults": 200, "typeEquals": "SYSTEM_DEFINED"}
    while True:
        response = client.list_inference_profiles(**kwargs)
        profiles.extend(response.get("inferenceProfileSummaries", []))
        if "nextToken" not in response:
            break
        kwargs["nextToken"] = response["nextToken"]
    return profiles


@router.get("/bedrock-models")
async def list_bedrock_models(db: AsyncSession = Depends(get_db)):
    """Fetch available text inference profiles from Bedrock, merged with known defaults."""
    import asyncio

    import boto3

    region = await get_config_value(db, "bedrock_region") or "us-east-1"
    aws_profile = await get_config_value(db, "bedrock_aws_profile")

    try:
        session = boto3.Session(profile_name=aws_profile or "default")
        client = session.client("bedrock", region_name=region)
        loop = asyncio.get_event_loop()
        all_profiles = await loop.run_in_executor(
            None,
            lambda: _paginate_inference_profiles(client),
        )
    except Exception as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=502, detail=f"Failed to list Bedrock models: {e}")

    models: dict[str, str] = {}
    for profile in all_profiles:
        profile_id = profile["inferenceProfileId"]
        name = profile.get("inferenceProfileName", profile_id)
        name_lower = name.lower()
        if any(kw in name_lower for kw in _EXCLUDE_KEYWORDS):
            continue
        if any(kw in name_lower for kw in _TEXT_MODEL_KEYWORDS):
            models[profile_id] = name

    result = [{"id": k, "label": v} for k, v in models.items()]
    result.sort(key=lambda m: m["label"])
    return result


@router.get("/bedrock-image-models")
async def list_bedrock_image_models(db: AsyncSession = Depends(get_db)):
    """Fetch available image model inference profiles from Bedrock."""
    import asyncio

    import boto3

    region = (
        await get_config_value(db, "bedrock_image_region")
        or await get_config_value(db, "bedrock_region")
        or "us-east-1"
    )
    aws_profile = await get_config_value(db, "bedrock_aws_profile")

    try:
        session = boto3.Session(profile_name=aws_profile or "default")
        client = session.client("bedrock", region_name=region)
        loop = asyncio.get_event_loop()
        all_profiles = await loop.run_in_executor(
            None,
            lambda: _paginate_inference_profiles(client),
        )
    except Exception as e:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=502,
            detail=f"Failed to list Bedrock image models: {e}",
        )

    models: dict[str, str] = {}
    for profile in all_profiles:
        profile_id = profile["inferenceProfileId"]
        name = profile.get("inferenceProfileName", profile_id)
        name_lower = name.lower()
        if any(kw in name_lower for kw in _IMAGE_MODEL_KEYWORDS):
            models[profile_id] = name

    result = [{"id": k, "label": v} for k, v in models.items()]
    result.sort(key=lambda m: m["label"])
    return result
