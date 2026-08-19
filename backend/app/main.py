from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app import paths
from app.api import (
    ai,
    auth,
    backup,
    chapters,
    codex,
    comments,
    config,
    conversations,
    cover,
    export,
    fonts,
    gallery,
    gdrive,
    images,
    imports,
    narration,
    profiles,
    scenes,
    sections,
    series,
    uploads,
    works,
)
from app.db.engine import init_db
from app.logging_config import setup_logging
from app.middleware import RequestLoggingMiddleware

setup_logging()
logger = logging.getLogger("typecast.app")

DATA_DIR = paths.DATA_DIR
UPLOAD_DIR = paths.UPLOAD_DIR
_static_env = os.environ.get("TYPECAST_STATIC_DIR", "")
STATIC_DIR = Path(_static_env) if _static_env else None


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Typecast (data_dir=%s)", DATA_DIR)
    await init_db()
    logger.info("Database initialized")
    yield
    logger.info("Shutting down Typecast")


def create_app() -> FastAPI:
    app = FastAPI(title="Typecast", version="0.1.0", lifespan=lifespan)

    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
    app.include_router(series.router, prefix="/api/series", tags=["series"])
    app.include_router(works.router, prefix="/api/works", tags=["works"])
    app.include_router(chapters.router, prefix="/api", tags=["chapters"])
    app.include_router(scenes.router, prefix="/api", tags=["scenes"])
    app.include_router(comments.router, prefix="/api", tags=["comments"])
    app.include_router(codex.router, prefix="/api/codex", tags=["codex"])
    app.include_router(sections.router, prefix="/api", tags=["sections"])
    app.include_router(imports.router, prefix="/api", tags=["import"])
    app.include_router(profiles.router, prefix="/api/profiles", tags=["profiles"])
    app.include_router(uploads.router, prefix="/api", tags=["uploads"])
    app.include_router(fonts.router, prefix="/api/fonts", tags=["fonts"])
    app.include_router(images.router, prefix="/api", tags=["images"])
    app.include_router(gallery.router, prefix="/api/gallery", tags=["gallery"])
    app.include_router(export.router, prefix="/api", tags=["export"])
    app.include_router(cover.router, prefix="/api/cover", tags=["cover"])
    app.include_router(config.router, prefix="/api/config", tags=["config"])
    app.include_router(ai.router, prefix="/api/ai", tags=["ai"])
    app.include_router(narration.router, prefix="/api/narration", tags=["narration"])
    app.include_router(conversations.router, prefix="/api/conversations", tags=["conversations"])
    app.include_router(backup.router, prefix="/api/backup", tags=["backup"])
    app.include_router(gdrive.router, prefix="/api/gdrive", tags=["gdrive"])

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
        )

    @app.get("/api/health")
    async def health_check():
        return {"status": "ok"}

    if STATIC_DIR and STATIC_DIR.is_dir():
        app.mount(
            "/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static"
        )

    return app


app = create_app()
