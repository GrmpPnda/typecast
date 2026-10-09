from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

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
    users,
    works,
)
from app.api.deps import get_current_user, require_admin
from app.api.ownership import enforce_path_ownership
from app.db.engine import init_db
from app.logging_config import setup_logging
from app.middleware import RequestLoggingMiddleware

setup_logging()
logger = logging.getLogger("typecast.app")

DATA_DIR = paths.DATA_DIR
UPLOAD_DIR = paths.UPLOAD_DIR
_static_env = os.environ.get("TYPECAST_STATIC_DIR", "")
STATIC_DIR = Path(_static_env) if _static_env else None

# Behind a TLS-terminating proxy, turn on the HTTPS redirect and HSTS. Off by
# default because development runs on plain http and a redirect would break it.
# Requires uvicorn --proxy-headers, or every request still looks like http and
# the redirect loops.
FORCE_HTTPS = os.environ.get("TYPECAST_FORCE_HTTPS", "0") == "1"
HSTS_MAX_AGE = int(os.environ.get("TYPECAST_HSTS_MAX_AGE", "31536000"))

# Off unless configured. The frontend is always served from the same origin as
# the API (by the backend itself, by nginx, or through the Vite dev proxy), so
# the browser never needs CORS. The old default of "*" with credentials made
# Starlette echo any requesting origin and allow credentials whenever a cookie
# was present, and under single sign-on the session *is* a cookie: any website
# you visited while signed in could read your manuscripts.
_origins_env = os.environ.get("TYPECAST_CORS_ORIGINS", "").strip()
CORS_ORIGINS = [o.strip() for o in _origins_env.split(",") if o.strip()]


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Typecast (data_dir=%s)", DATA_DIR)
    from app.services.auth import AUTH_MODE

    if AUTH_MODE == "proxy":
        # Raises, stopping startup, if there is no way to tell real users from
        # requests with forged identity headers.
        from app.services import sso

        sso.validate_config()
    await init_db()
    logger.info("Database initialized")
    yield
    logger.info("Shutting down Typecast")


class SinglePageApp(StaticFiles):
    """Serve the built frontend, falling back to index.html for its own routes.

    Paths like /work/<id> or /settings exist only in the browser router. Plain
    StaticFiles answered a direct load, a refresh, or a bookmark of one of them
    with {"detail": "Not Found"}. The compose stack never showed it because its
    nginx has this fallback; the single-container image, which is what Azure
    runs, had none. Unknown /api and /uploads paths still 404, so a typo in an
    API call is not answered with a web page.
    """

    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404 or path.split("/", 1)[0] in ("api", "uploads"):
                raise
            logger.debug("SPA fallback to index.html for /%s", path)
            return await super().get_response("index.html", scope)


def create_app() -> FastAPI:
    app = FastAPI(title="Typecast", version="0.1.0", lifespan=lifespan)

    app.add_middleware(RequestLoggingMiddleware)
    if CORS_ORIGINS:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=CORS_ORIGINS,
            # Never with a wildcard: that combination is the vulnerability above.
            allow_credentials="*" not in CORS_ORIGINS,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    if FORCE_HTTPS:
        # The scheme is the one --proxy-headers derives from X-Forwarded-Proto,
        # so this works behind a TLS-terminating proxy. /api/health is exempt:
        # container health probes call it over plain HTTP from inside the
        # network, and a redirect would read as a failure or a false success.
        logger.info("HTTPS enforcement on (HSTS max-age=%ds)", HSTS_MAX_AGE)

        @app.middleware("http")
        async def enforce_https(request: Request, call_next):
            if request.url.scheme == "http" and request.url.path != "/api/health":
                target = request.url.replace(scheme="https")
                logger.debug("Redirecting plain HTTP request to %s", target)
                # 308 keeps the method and body, so a POST is not turned into a GET.
                return RedirectResponse(str(target), status_code=308)
            response = await call_next(request)
            if request.url.scheme == "https":
                response.headers["Strict-Transport-Security"] = (
                    f"max-age={HSTS_MAX_AGE}; includeSubDomains"
                )
            return response

    # Every router requires a signed-in account and owns-the-resource checks on
    # any ID in the path. These used to be absent on 89 of 113 routes: the login
    # screen gated only the UI. Routers that need less are explicit below.
    signed_in = [Depends(get_current_user), Depends(enforce_path_ownership)]
    admin_only = [Depends(require_admin)]

    # auth checks per route: login, setup, and mode must work without a token.
    app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
    app.include_router(users.router, prefix="/api/users", tags=["users"], dependencies=admin_only)
    app.include_router(backup.router, prefix="/api/backup", tags=["backup"],
                       dependencies=admin_only)
    # The Drive connection belongs to the install owner's Google account.
    app.include_router(gdrive.router, prefix="/api/gdrive", tags=["gdrive"],
                       dependencies=admin_only + signed_in[1:])
    app.include_router(gdrive.public_router, prefix="/api/gdrive", tags=["gdrive"])

    for router, prefix, tag in (
        (series.router, "/api/series", "series"),
        (works.router, "/api/works", "works"),
        (chapters.router, "/api", "chapters"),
        (scenes.router, "/api", "scenes"),
        (comments.router, "/api", "comments"),
        (codex.router, "/api/codex", "codex"),
        (sections.router, "/api", "sections"),
        (imports.router, "/api", "import"),
        (profiles.router, "/api/profiles", "profiles"),
        (uploads.router, "/api", "uploads"),
        (fonts.router, "/api/fonts", "fonts"),
        (images.router, "/api", "images"),
        (gallery.router, "/api/gallery", "gallery"),
        (export.router, "/api", "export"),
        (cover.router, "/api/cover", "cover"),
        (config.router, "/api/config", "config"),
        (ai.router, "/api/ai", "ai"),
        (narration.router, "/api/narration", "narration"),
        (conversations.router, "/api/conversations", "conversations"),
    ):
        app.include_router(router, prefix=prefix, tags=[tag], dependencies=signed_in)

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
        # The deploy workflow polls this until the version matches the commit it
        # just shipped, so it knows the new revision is the one answering.
        return {"status": "ok", "version": os.environ.get("TYPECAST_VERSION", "dev")}

    if STATIC_DIR and STATIC_DIR.is_dir():
        app.mount("/", SinglePageApp(directory=str(STATIC_DIR), html=True), name="static")

    return app


app = create_app()
