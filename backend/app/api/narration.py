from __future__ import annotations

import json
import logging
import uuid

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.db.engine import async_session_factory
from app.services.narration import POLLY_VOICES, synthesize_scene_streaming

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/voices")
async def list_voices():
    return POLLY_VOICES


@router.get("/works/{work_id}/scenes/{scene_id}/narrate")
async def narrate_scene(
    work_id: uuid.UUID,
    scene_id: uuid.UUID,
):
    async def event_stream():
        async with async_session_factory() as db:
            try:
                async for event in synthesize_scene_streaming(
                    db, str(scene_id), str(work_id)
                ):
                    yield f"data: {json.dumps(event)}\n\n"
            except ValueError as e:
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
            except Exception as e:
                name = type(e).__name__
                msg = str(e)
                if "ExpiredToken" in msg or "expired" in msg.lower():
                    detail = "AWS security token has expired. Refresh your credentials."
                elif "AccessDenied" in msg or "NotAuthorized" in msg:
                    detail = "AWS credentials lack polly:SynthesizeSpeech permission."
                else:
                    detail = f"Polly error: {name}: {msg}"
                logger.error("Narration failed: %s: %s", name, msg)
                yield f"data: {json.dumps({'type': 'error', 'message': detail})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
