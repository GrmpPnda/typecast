from __future__ import annotations

import base64
import json
import logging
import uuid

import aiofiles
from sqlalchemy.ext.asyncio import AsyncSession

from app import paths
from app.api.config import get_config_value

log = logging.getLogger(__name__)

UPLOAD_DIR = paths.UPLOAD_DIR


BEDROCK_IMAGE_MODELS = {
    "amazon.nova-canvas-v1:0",
    "stability.sd3-5-large-v1:0",
    "stability.sd3-large-v1:0",
    "stability.stable-image-core-v1:0",
}


async def generate_image(
    db: AsyncSession,
    prompt: str,
    *,
    negative_prompt: str = "",
    width: int = 1024,
    height: int = 1024,
    reference_images: list[dict] | None = None,
) -> dict:
    """Generate an image using the configured provider. Returns {"data": base64, "mime_type": ...}"""
    image_provider = await get_config_value(db, "image_provider")
    image_model = await get_config_value(db, "image_model")

    if not image_provider:
        image_provider = await get_config_value(db, "ai_provider")

    if image_provider == "bedrock":
        model_id = image_model or "amazon.nova-canvas-v1:0"
        return await _generate_bedrock(db, prompt, negative_prompt, width, height, reference_images, model_id)
    elif image_provider == "openai":
        model_id = image_model or "dall-e-3"
        return await _generate_openai(db, prompt, width, height, model_id, reference_images)
    else:
        raise ValueError(
            "Image generation requires Bedrock or OpenAI as the image provider. "
            "Anthropic does not support image generation. "
            "Configure an image provider in Settings."
        )


async def _generate_bedrock(
    db: AsyncSession,
    prompt: str,
    negative_prompt: str,
    width: int,
    height: int,
    reference_images: list[dict] | None,
    model_id: str,
) -> dict:
    """Generate via a Bedrock image model (Nova Canvas or Stability AI)."""
    import asyncio

    import boto3
    from botocore.config import Config as BotoConfig

    region = (
        await get_config_value(db, "bedrock_image_region")
        or await get_config_value(db, "bedrock_region")
        or "us-east-1"
    )
    aws_profile = await get_config_value(db, "bedrock_aws_profile")
    session = boto3.Session(profile_name=aws_profile or "default")
    client = session.client(
        "bedrock-runtime",
        region_name=region,
        config=BotoConfig(read_timeout=120, connect_timeout=10),
    )

    if model_id.startswith("stability."):
        body = _build_stability_body(prompt, negative_prompt, width, height)
    else:
        body = _build_nova_canvas_body(prompt, negative_prompt, width, height, reference_images)

    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(
        None,
        lambda: client.invoke_model(
            modelId=model_id,
            body=json.dumps(body),
            contentType="application/json",
            accept="application/json",
        ),
    )

    result = json.loads(response["body"].read())

    if model_id.startswith("stability."):
        image_b64 = result["images"][0]
    else:
        image_b64 = result["images"][0]

    return {"data": image_b64, "mime_type": "image/png"}


def _build_nova_canvas_body(
    prompt: str,
    negative_prompt: str,
    width: int,
    height: int,
    reference_images: list[dict] | None,
) -> dict:
    if reference_images and len(reference_images) > 0:
        ref = reference_images[0]
        body: dict = {
            "taskType": "COLOR_GUIDED_GENERATION",
            "colorGuidedGenerationParams": {
                "text": prompt,
                "referenceImage": ref["data"],
                "colors": [],
            },
            "imageGenerationConfig": {
                "width": width,
                "height": height,
                "numberOfImages": 1,
                "quality": "premium",
            },
        }
    else:
        body = {
            "taskType": "TEXT_IMAGE",
            "textToImageParams": {
                "text": prompt,
            },
            "imageGenerationConfig": {
                "width": width,
                "height": height,
                "numberOfImages": 1,
                "quality": "premium",
            },
        }
    if negative_prompt and "textToImageParams" in body:
        body["textToImageParams"]["negativeText"] = negative_prompt
    return body


def _build_stability_body(
    prompt: str,
    negative_prompt: str,
    width: int,
    height: int,
) -> dict:
    body: dict = {
        "prompt": prompt,
        "mode": "text-to-image",
        "output_format": "png",
    }
    if negative_prompt:
        body["negative_prompt"] = negative_prompt
    if width and height:
        body["aspect_ratio"] = _nearest_aspect_ratio(width, height)
    return body


def _nearest_aspect_ratio(width: int, height: int) -> str:
    """Map dimensions to nearest Stability AI supported aspect ratio."""
    ratio = width / height
    options = [
        (1 / 1, "1:1"),
        (16 / 9, "16:9"),
        (9 / 16, "9:16"),
        (21 / 9, "21:9"),
        (9 / 21, "9:21"),
        (3 / 2, "3:2"),
        (2 / 3, "2:3"),
        (4 / 5, "4:5"),
        (5 / 4, "5:4"),
    ]
    return min(options, key=lambda x: abs(x[0] - ratio))[1]


async def _generate_openai(
    db: AsyncSession,
    prompt: str,
    width: int,
    height: int,
    model_id: str,
    reference_images: list[dict] | None = None,
) -> dict:
    """Generate via OpenAI image models (DALL-E 3, gpt-image-1, etc.)."""
    from openai import AsyncOpenAI

    api_key = await get_config_value(db, "openai_api_key")
    if not api_key:
        raise ValueError("OpenAI API key not configured. Set it in Settings.")

    client = AsyncOpenAI(api_key=api_key)

    if model_id == "gpt-image-1":
        size = "1024x1024"
        if width > height:
            size = "1536x1024"
        elif height > width:
            size = "1024x1536"

        kwargs: dict = {
            "model": model_id,
            "prompt": prompt,
            "n": 1,
            "size": size,
        }
        if reference_images:
            import io
            image_files = []
            for ref in reference_images:
                img_bytes = base64.b64decode(ref["data"])
                buf = io.BytesIO(img_bytes)
                buf.name = f"{ref.get('name', 'reference')}.png"
                image_files.append(buf)
            kwargs["image"] = image_files

        response = await client.images.edit(**kwargs) if reference_images else await client.images.generate(**kwargs)

        import httpx
        async with httpx.AsyncClient() as http:
            img_resp = await http.get(response.data[0].url)
            image_b64 = base64.b64encode(img_resp.content).decode()
    else:
        size = "1024x1024"
        if width > height:
            size = "1792x1024"
        elif height > width:
            size = "1024x1792"
        response = await client.images.generate(
            model=model_id,
            prompt=prompt,
            n=1,
            size=size,
            response_format="b64_json",
        )
        image_b64 = response.data[0].b64_json

    return {"data": image_b64, "mime_type": "image/png"}


async def save_generated_image(
    db: AsyncSession,
    image_data: str,  # base64
    mime_type: str,
    *,
    work_id: uuid.UUID | None = None,
    codex_entry_id: uuid.UUID | None = None,
    alt_text: str = "",
    caption: str = "",
) -> dict:
    """Save a generated image to disk and database. Returns metadata dict."""
    image_bytes = base64.b64decode(image_data)
    ext = ".png" if "png" in mime_type else ".jpg"
    image_id = uuid.uuid4()
    filename = f"{image_id}{ext}"

    if work_id:
        from app.models.image import Image

        dest_dir = UPLOAD_DIR / "images" / str(work_id)
        dest_dir.mkdir(parents=True, exist_ok=True)

        async with aiofiles.open(dest_dir / filename, "wb") as f:
            await f.write(image_bytes)

        img = Image(
            id=image_id,
            work_id=work_id,
            filename=filename,
            original_name=f"ai-generated-{image_id}{ext}",
            mime_type=mime_type,
            size_bytes=len(image_bytes),
            alt_text=alt_text,
            caption=caption,
        )
        db.add(img)
        await db.commit()
        await db.refresh(img)

        return {
            "id": str(img.id),
            "url": img.url,
            "action": "saved_to_work_gallery",
            "work_id": str(work_id),
        }

    elif codex_entry_id:
        from app.models.codex_image import CodexImage
        from sqlalchemy import select

        # Check if entry has any existing images
        result = await db.execute(
            select(CodexImage).where(CodexImage.codex_entry_id == codex_entry_id)
        )
        existing = result.scalars().all()
        is_first = len(existing) == 0

        dest_dir = UPLOAD_DIR / "codex" / str(codex_entry_id)
        dest_dir.mkdir(parents=True, exist_ok=True)

        async with aiofiles.open(dest_dir / filename, "wb") as f:
            await f.write(image_bytes)

        img = CodexImage(
            id=image_id,
            codex_entry_id=codex_entry_id,
            filename=filename,
            original_name=f"ai-generated-{image_id}{ext}",
            mime_type=mime_type,
            size_bytes=len(image_bytes),
            alt_text=alt_text,
            is_primary=is_first,
        )
        db.add(img)
        await db.commit()
        await db.refresh(img)

        return {
            "id": str(img.id),
            "url": img.url,
            "is_primary": is_first,
            "action": "saved_to_codex",
            "codex_entry_id": str(codex_entry_id),
        }

    else:
        raise ValueError("Must provide either work_id or codex_entry_id")
