from __future__ import annotations

import base64
import json
import logging
import re
from collections.abc import AsyncIterator

import boto3
from botocore.exceptions import ClientError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.config import get_config_value
from app.models.codex import CodexEntry, EntryType
from app.models.codex_association import CodexAssociation
from app.models.scene import Scene

logger = logging.getLogger(__name__)

SEGMENTATION_PROMPT = """\
You are a text segmentation engine. Given a scene of fiction, split it into \
sequential segments, each labelled with WHO is speaking or "NARRATOR" for \
non-dialogue prose.

Rules:
- Dialogue is any text inside quotation marks attributed to a character.
- Everything else (narration, action, description) is NARRATOR.
- Preserve the EXACT original text in each segment — do not alter wording.
- Combine adjacent narrator segments into one.
- Output valid JSON: an array of objects with "speaker" and "text" fields.
- Speaker names must match character names exactly as they appear in the \
character list provided.

Characters:
{characters}

Scene text:
{scene_text}

Return ONLY the JSON array, no other text."""


async def _get_work_characters(db: AsyncSession, work_id: object) -> list[CodexEntry]:
    result = await db.execute(
        select(CodexEntry)
        .join(CodexAssociation, CodexAssociation.codex_entry_id == CodexEntry.id)
        .where(CodexAssociation.target_type == "work")
        .where(CodexAssociation.target_id == work_id)
        .where(CodexEntry.entry_type == EntryType.CHARACTER)
    )
    return list(result.scalars().all())


async def _segment_scene(
    db: AsyncSession, scene_content: str, characters: list[CodexEntry]
) -> list[dict]:
    from app.services.ai import get_ai_provider

    char_list = "\n".join(f"- {c.name}" for c in characters) or "- (no named characters)"
    prompt = SEGMENTATION_PROMPT.format(
        characters=char_list,
        scene_text=scene_content[:8000],
    )

    provider = await get_ai_provider(db)
    response = await provider.generate(prompt)

    match = re.search(r"\[.*\]", response, re.DOTALL)
    if not match:
        return [{"speaker": "NARRATOR", "text": scene_content}]

    try:
        segments = json.loads(match.group())
    except json.JSONDecodeError:
        return [{"speaker": "NARRATOR", "text": scene_content}]

    return segments


def _build_voice_map(
    characters: list[CodexEntry], narrator_voice: str
) -> dict[str, str]:
    voice_map: dict[str, str] = {"NARRATOR": narrator_voice}
    for char in characters:
        if char.voice_id:
            voice_map[char.name] = char.voice_id
    return voice_map


def _get_polly_client(region: str, profile: str = "default"):
    session = boto3.Session(profile_name=profile)
    client = session.client("polly", region_name=region)
    return client


def _verify_polly_credentials(client) -> None:
    """Quick check that AWS credentials are valid before starting synthesis."""
    try:
        client.describe_voices(LanguageCode="en-US")
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        if code in ("ExpiredTokenException", "UnrecognizedClientException"):
            raise ValueError("AWS security token has expired. Refresh your credentials.")
        if code in ("AccessDeniedException",):
            raise ValueError("AWS credentials lack Polly permissions.")
        raise


def _clean_for_ssml(text: str) -> str:
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    text = text.replace('"', "&quot;")
    text = text.replace("'", "&apos;")
    return text


_MAX_SSML_CHARS = 2500


def _chunk_text(text: str, max_len: int = _MAX_SSML_CHARS) -> list[str]:
    if len(text) <= max_len:
        return [text]
    chunks: list[str] = []
    while text:
        if len(text) <= max_len:
            chunks.append(text)
            break
        cut = text.rfind(". ", 0, max_len)
        if cut == -1:
            cut = text.rfind(" ", 0, max_len)
        if cut == -1:
            cut = max_len
        else:
            cut += 1
        chunks.append(text[:cut].strip())
        text = text[cut:].strip()
    return chunks


_ENGINE_FALLBACK = ["long-form", "generative", "neural"]


def _synthesize_chunk(client, ssml: str, voice_id: str, engine: str) -> bytes:
    try:
        resp = client.synthesize_speech(
            OutputFormat="mp3", TextType="ssml", Text=ssml,
            VoiceId=voice_id, Engine=engine,
        )
        return resp["AudioStream"].read()
    except ClientError:
        pass

    for fallback in _ENGINE_FALLBACK:
        if fallback == engine:
            continue
        try:
            resp = client.synthesize_speech(
                OutputFormat="mp3", TextType="ssml", Text=ssml,
                VoiceId=voice_id, Engine=fallback,
            )
            return resp["AudioStream"].read()
        except ClientError:
            continue
    raise ValueError(f"No compatible engine for voice {voice_id}")


def _synthesize_segment(
    client,
    text: str,
    voice_id: str,
    engine: str,
) -> bytes:
    chunks = _chunk_text(text)
    audio_parts: list[bytes] = []
    for chunk in chunks:
        clean = _clean_for_ssml(chunk)
        ssml = f'<speak><prosody rate="medium">{clean}</prosody></speak>'
        audio_parts.append(_synthesize_chunk(client, ssml, voice_id, engine))
    return b"".join(audio_parts)


def _split_into_paragraphs(content: str) -> list[dict]:
    """Split scene content into paragraph-based segments for simple narration."""
    paragraphs = [p.strip() for p in content.split("\n") if p.strip()]
    segments = []
    for p in paragraphs:
        if p.startswith("#") or p == "---" or p == "***":
            continue
        segments.append({"speaker": "NARRATOR", "text": p})
    return segments if segments else [{"speaker": "NARRATOR", "text": content.strip()}]


async def synthesize_scene_streaming(
    db: AsyncSession,
    scene_id: str,
    work_id: str,
) -> AsyncIterator[dict]:
    """Stream narration events segment-by-segment.

    Event types:
    - segments: initial metadata (segment list with speaker/text)
    - audio: base64-encoded mp3 for one segment
    - done: all segments synthesized
    - error: something went wrong

    If no characters have voice assignments, skips AI segmentation and uses
    paragraph-based chunking for immediate playback start.
    """
    import asyncio
    import uuid as _uuid
    scene_uuid = _uuid.UUID(scene_id)
    work_uuid = _uuid.UUID(work_id)

    polly_enabled = await get_config_value(db, "polly_enabled")
    if polly_enabled != "true":
        raise ValueError("Polly narration is not enabled")

    region = await get_config_value(db, "polly_region")
    narrator_voice = await get_config_value(db, "polly_narrator_voice")
    engine = await get_config_value(db, "polly_engine")
    aws_profile = await get_config_value(db, "polly_aws_profile") or "default"

    if not region or not narrator_voice or not engine:
        raise ValueError("Narration not fully configured. Check Settings.")

    result = await db.execute(select(Scene).where(Scene.id == scene_uuid))
    scene = result.scalar_one_or_none()
    if scene is None:
        raise ValueError("Scene not found")

    content = scene.content or ""
    if not content.strip():
        raise ValueError("Scene has no content")

    client = _get_polly_client(region, aws_profile)
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _verify_polly_credentials, client)

    characters = await _get_work_characters(db, work_uuid)
    voice_map = _build_voice_map(characters, narrator_voice)

    has_character_voices = any(c.voice_id for c in characters)

    if has_character_voices:
        logger.info("Segmenting scene %s with AI (character voices detected)", scene_id)
        segments = await _segment_scene(db, content, characters)
    else:
        logger.info("Using paragraph segmentation for scene %s (no character voices)", scene_id)
        segments = _split_into_paragraphs(content)

    yield {
        "type": "segments",
        "segments": [
            {"index": i, "speaker": s.get("speaker", "NARRATOR"), "text": s.get("text", "")}
            for i, s in enumerate(segments)
        ],
    }

    for i, segment in enumerate(segments):
        speaker = segment.get("speaker", "NARRATOR")
        text = segment.get("text", "")
        if not text.strip():
            continue

        voice = voice_map.get(speaker, narrator_voice)
        logger.debug("Synthesizing segment %d (%s) with voice %s", i, speaker, voice)

        audio_bytes = await loop.run_in_executor(
            None, _synthesize_segment, client, text, voice, engine
        )
        audio_b64 = base64.b64encode(audio_bytes).decode("ascii")

        yield {
            "type": "audio",
            "index": i,
            "audio": audio_b64,
        }

    yield {"type": "done"}


_LF = "long-form"
_NR = "neural"
_GN = "generative"
_ALL = [_LF, _NR, _GN]
_LN = [_LF, _NR]
_NG = [_NR, _GN]

POLLY_VOICES = [
    {"id": "Ruth", "name": "Ruth", "gender": "Female", "language": "en-US", "engines": _ALL},
    {"id": "Matthew", "name": "Matthew", "gender": "Male", "language": "en-US", "engines": _ALL},
    {"id": "Joanna", "name": "Joanna", "gender": "Female", "language": "en-US", "engines": _LN},
    {"id": "Stephen", "name": "Stephen", "gender": "Male", "language": "en-US", "engines": _LN},
    {"id": "Danielle", "name": "Danielle", "gender": "Female",
     "language": "en-US", "engines": _ALL},
    {"id": "Gregory", "name": "Gregory", "gender": "Male", "language": "en-US", "engines": _ALL},
    {"id": "Amy", "name": "Amy", "gender": "Female", "language": "en-GB", "engines": _ALL},
    {"id": "Brian", "name": "Brian", "gender": "Male", "language": "en-GB", "engines": _ALL},
    {"id": "Arthur", "name": "Arthur", "gender": "Male", "language": "en-GB", "engines": _NG},
    {"id": "Olivia", "name": "Olivia", "gender": "Female", "language": "en-AU", "engines": _NG},
    {"id": "Aria", "name": "Aria", "gender": "Female", "language": "en-NZ", "engines": [_NR]},
    {"id": "Ayanda", "name": "Ayanda", "gender": "Female", "language": "en-ZA", "engines": [_NR]},
    {"id": "Ivy", "name": "Ivy", "gender": "Female (child)", "language": "en-US", "engines": _NG},
    {"id": "Kevin", "name": "Kevin", "gender": "Male (child)", "language": "en-US", "engines": _NG},
    {"id": "Salli", "name": "Salli", "gender": "Female", "language": "en-US", "engines": _NG},
    {"id": "Kimberly", "name": "Kimberly", "gender": "Female", "language": "en-US", "engines": _NG},
    {"id": "Kendra", "name": "Kendra", "gender": "Female", "language": "en-US", "engines": _NG},
    {"id": "Justin", "name": "Justin", "gender": "Male", "language": "en-US", "engines": _NG},
    {"id": "Joey", "name": "Joey", "gender": "Male", "language": "en-US", "engines": _NG},
]
