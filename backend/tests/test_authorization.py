"""Authentication and authorization on every API route.

Until this existed, 89 of 113 routes accepted a request with no credentials,
including GET/PUT/DELETE on any work by ID. The login screen gated only the UI.

Three layers, all derived from the live route table so a new route cannot slip
through unclassified:

1. Every route is public by explicit allowlist, administrator-only, or
   requires a signed-in account.
2. Every route that takes a resource ID in its path carries the matching
   ownership dependency from app/api/ownership.py.
3. A second account probes every such route with the first account's IDs and
   must get 404, while the owner gets through. This catches a dependency that
   is present but wired to the wrong parameter.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import ownership
from app.api.deps import get_current_user, require_admin
from app.db.engine import get_db
from app.main import create_app
from app.models.chapter import Chapter
from app.models.codex import CodexEntry, EntryType
from app.models.codex_association import CodexAssociation
from app.models.codex_image import CodexImage
from app.models.comment import Comment
from app.models.conversation import Conversation
from app.models.font import Font
from app.models.image import Image
from app.models.profile import Profile, ProfileFormat
from app.models.scene import Scene
from app.models.section import Section, SectionPlacement, SectionType
from app.models.series import Series
from app.models.user import User
from app.models.work import Work
from app.services.auth import hash_password
from tests.routes import api_routes

# --- policy --------------------------------------------------------------------------

PUBLIC = {
    ("GET", "/api/health"),
    ("GET", "/api/auth/mode"),
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/register"),  # closed unless TYPECAST_OPEN_REGISTRATION=1
    ("POST", "/api/auth/setup"),  # refuses once any account exists
    ("GET", "/api/gdrive/callback"),  # Google's redirect; guarded by single-use state
    ("DELETE", "/api/auth/session"),  # sign-out: only clears the caller's own cookie
}

# Install-wide settings and shared resources: readable by any account, but only an
# administrator may change them, because a change affects every account.
ADMIN_ONLY = [
    (r".*", r"/api/users/.*"),
    (r".*", r"/api/backup/.*"),
    (r"PUT", r"/api/config/"),
    (r"GET", r"/api/config/bedrock-(image-)?models"),
    (r"POST|PUT|DELETE", r"/api/fonts(/\{font_id\})?"),
    (r"POST|PUT|DELETE", r"/api/profiles/(\{profile_id\})?"),
    # The Drive connection is the install owner's Google account.
    (r".*", r"/api/gdrive/(?!callback$).*"),
]

SHARED_PARAMS = ownership.NOT_OWNED_PARAMS  # install-wide resources and accounts


def _api_routes():
    for method, path, route in api_routes(create_app()):
        if path.startswith("/api"):
            yield method, path, route


def _calls(route) -> set:
    found = set()

    def walk(dependant):
        for sub in dependant.dependencies:
            if sub.call is not None:
                found.add(sub.call)
            walk(sub)

    walk(route.dependant)
    return found


def _is_admin_only(method: str, path: str) -> bool:
    return any(
        re.fullmatch(m, method) and re.fullmatch(p, path) for m, p in ADMIN_ONLY
    )


ROUTES = list(_api_routes())
ROUTE_IDS = [f"{m} {p}" for m, p, _ in ROUTES]


def _ids(pairs):
    return [f"{m} {p}" for m, p in pairs]


# --- 1 and 2: static, from the route table ---------------------------------------


@pytest.mark.parametrize(("method", "path", "route"), ROUTES, ids=ROUTE_IDS)
def test_every_route_declares_who_may_call_it(method, path, route):
    calls = _calls(route)
    if (method, path) in PUBLIC:
        return
    if _is_admin_only(method, path):
        assert require_admin in calls, f"{method} {path} must be administrator-only"
    else:
        assert get_current_user in calls or require_admin in calls, (
            f"{method} {path} accepts unauthenticated requests"
        )


@pytest.mark.parametrize(("method", "path", "route"), ROUTES, ids=ROUTE_IDS)
def test_every_resource_id_in_a_path_is_ownership_checked(method, path, route):
    params = [p for p in re.findall(r"\{(\w+)\}", path) if p not in SHARED_PARAMS]
    if not params:
        return
    for param in params:
        assert ownership.ownership_kind(path, param) is not None, (
            f"{path}: no ownership rule for {{{param}}}; add it to app/api/ownership.py"
        )
    assert ownership.enforce_path_ownership in _calls(route), (
        f"{method} {path} does not check ownership of {params}"
    )


def test_the_policy_names_only_routes_that_exist():
    """A stale allowlist entry would hide a renamed, unprotected route."""
    existing = {(m, p) for m, p, _ in ROUTES}
    assert PUBLIC <= existing, sorted(PUBLIC - existing)


def test_the_route_table_is_actually_populated():
    """Every check above is generated from ROUTES. If walking the app ever
    returns only the routes defined directly on it, as iterating app.routes does
    on FastAPI 0.143, they all pass vacuously."""
    assert len(ROUTES) > 100, f"only {len(ROUTES)} routes found; the walker is broken"
    assert any(p.startswith("/api/works/{work_id}") for _, p, _ in ROUTES)


# --- 3: dynamic, two accounts --------------------------------------------------------


async def _add(session_factory, *objects):
    async with session_factory() as session:
        session.add_all(objects)
        await session.commit()


def _user(email: str, *, admin: bool = False) -> User:
    return User(
        id=uuid.uuid4(), email=email, username=email.split("@")[0], display_name=email,
        hashed_password=hash_password("x" * 12), is_admin=admin,
    )


@pytest_asyncio.fixture
async def two_accounts(session_factory):
    """Alice owns one of everything; Bob is a separate account that owns nothing."""
    alice, bob = _user("alice@example.com"), _user("bob@example.com")
    series = Series(id=uuid.uuid4(), title="Alice's Saga", user_id=alice.id)
    work = Work(id=uuid.uuid4(), title="Alice's Novel", author="A", user_id=alice.id,
                series_id=series.id)
    chapter = Chapter(id=uuid.uuid4(), work_id=work.id, title="One", number=1, sort_order=0)
    scene = Scene(id=uuid.uuid4(), chapter_id=chapter.id, content="Private prose.", sort_order=0)
    comment = Comment(id=uuid.uuid4(), scene_id=scene.id, anchor_text="Private", content="x")
    section = Section(id=uuid.uuid4(), work_id=work.id, section_type=SectionType.DEDICATION,
                      placement=SectionPlacement.FRONT_MATTER)
    image = Image(id=uuid.uuid4(), work_id=work.id, filename="a.png", original_name="a.png",
                  mime_type="image/png", size_bytes=1)
    entry = CodexEntry(id=uuid.uuid4(), name="Secret", entry_type=EntryType.CHARACTER,
                       user_id=alice.id)
    association = CodexAssociation(id=uuid.uuid4(), codex_entry_id=entry.id,
                                   target_type="work", target_id=work.id)
    codex_image = CodexImage(id=uuid.uuid4(), codex_entry_id=entry.id, filename="c.png",
                             original_name="c.png", mime_type="image/png", size_bytes=1)
    conversation = Conversation(id=uuid.uuid4(), user_id=alice.id, work_id=work.id)
    font = Font(id=uuid.uuid4(), filename="f.ttf", original_name="f.ttf", family_name="F",
                mime_type="font/ttf", size_bytes=1)
    profile = Profile(id=uuid.uuid4(), name="Custom", format=ProfileFormat.PDF)
    for batch in (
        (alice, bob, font, profile),
        (series, entry),
        (work,),
        (chapter, section, image, association, codex_image, conversation),
        (scene,),
        (comment,),
    ):
        await _add(session_factory, *batch)
    ids = {
        "work_id": work.id, "series_id": series.id, "chapter_id": chapter.id,
        "scene_id": scene.id, "comment_id": comment.id, "section_id": section.id,
        "conversation_id": conversation.id, "entry_id": entry.id,
        "image_id": image.id, "codex_image_id": codex_image.id,
        "font_id": font.id, "profile_id": profile.id, "user_id": alice.id,
    }
    return alice, bob, ids


def _client_as(session_factory, user: User) -> AsyncClient:
    app = create_app()

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: user
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _fill(path: str, ids: dict) -> str:
    def value(match):
        name = match.group(1)
        if name == "image_id" and path.startswith("/api/codex/"):
            return str(ids["codex_image_id"])
        return str(ids[name])

    return re.sub(r"\{(\w+)\}", value, path)


OWNED_ROUTES = [
    (m, p) for m, p, _ in ROUTES
    if (m, p) not in PUBLIC
    and not _is_admin_only(m, p)
    and set(re.findall(r"\{(\w+)\}", p)) - SHARED_PARAMS
]


@pytest.mark.parametrize(("method", "path"), OWNED_ROUTES, ids=_ids(OWNED_ROUTES))
async def test_another_account_cannot_reach_your_resources(session_factory, two_accounts,
                                                           method, path):
    """Bob, signed in, uses Alice's IDs. Every route must say it does not exist."""
    _alice, bob, ids = two_accounts
    async with _client_as(session_factory, bob) as ac:
        resp = await ac.request(method, _fill(path, ids))
    assert resp.status_code == 404, (
        f"{method} {path} as another account returned {resp.status_code}: {resp.text[:200]}"
    )


# Streaming and rendering endpoints need real content to do anything; everything
# else must at least get past the ownership check for the owner.
OWNER_ROUTES = [(m, p) for m, p in OWNED_ROUTES if "narrate" not in p and "export" not in p]


@pytest.mark.parametrize(("method", "path"), OWNER_ROUTES, ids=_ids(OWNER_ROUTES))
async def test_the_owner_still_gets_through(session_factory, two_accounts, method, path):
    """The checks must not lock out the person who owns the resource.

    Every method, not only GET: on FastAPI 0.143 the codex-image routes (PATCH
    and DELETE) refused their own owner, and a GET-only check could not see it.
    An empty body earns a 422 from validation, which is fine; a 404 means the
    ownership check refused the owner.
    """
    alice, _bob, ids = two_accounts
    async with _client_as(session_factory, alice) as ac:
        resp = await ac.request(method, _fill(path, ids))
    assert resp.status_code != 404, (
        f"{method} {path} hid the owner's own resource: {resp.text[:200]}"
    )
    # 502 is an upstream service (the AI provider has no key in tests) failing
    # after the request was let through, which is what this test is about.
    assert resp.status_code < 500 or resp.status_code == 502, (
        f"{method} {path}: {resp.status_code} {resp.text[:200]}"
    )


ADMIN_ROUTES = [(m, p) for m, p, _ in ROUTES if _is_admin_only(m, p)]


@pytest.mark.parametrize(("method", "path"), ADMIN_ROUTES, ids=_ids(ADMIN_ROUTES))
async def test_administrator_routes_refuse_other_accounts(session_factory, two_accounts,
                                                          method, path):
    _alice, bob, ids = two_accounts
    async with _client_as(session_factory, bob) as ac:
        resp = await ac.request(method, _fill(path, ids))
    assert resp.status_code == 403, f"{method} {path} returned {resp.status_code}"


async def test_unauthenticated_requests_are_refused_end_to_end(session_factory, monkeypatch):
    """No dependency override: the real token check, in multi-user mode."""
    for module in ("app.services.auth", "app.api.auth", "app.api.deps"):
        monkeypatch.setattr(f"{module}.AUTH_MODE", "multi", raising=False)
        monkeypatch.setattr(f"{module}.NO_AUTOLOGIN", False, raising=False)
    app = create_app()

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    probe = uuid.uuid4()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        for method, path, _ in ROUTES:
            if (method, path) in PUBLIC:
                continue
            url = re.sub(r"\{\w+\}", str(probe), path)
            resp = await ac.request(method, url)
            assert resp.status_code == 401, f"{method} {path} without a token: {resp.status_code}"


# --- lists and request bodies --------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    ["/api/works/", "/api/series/", "/api/codex/", "/api/images/all", "/api/conversations/",
     "/api/gallery"],
)
async def test_lists_show_only_your_own(session_factory, two_accounts, path):
    _alice, bob, _ids = two_accounts
    async with _client_as(session_factory, bob) as ac:
        resp = await ac.get(path)
    assert resp.status_code == 200, resp.text[:200]
    assert resp.json() == [], f"{path} showed another account's items to Bob"


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/api/codex/", lambda ids: {"name": "x", "entry_type": "character",
                                      "work_ids": [str(ids["work_id"])]}),
        ("/api/codex/", lambda ids: {"name": "x", "entry_type": "character",
                                      "series_ids": [str(ids["series_id"])]}),
        ("/api/works/", lambda ids: {"title": "x", "author": "y",
                                      "series_id": str(ids["series_id"])}),
        ("/api/conversations/", lambda ids: {"work_id": str(ids["work_id"])}),
        ("/api/ai/chat", lambda ids: {"prompt": "hi", "work_id": str(ids["work_id"])}),
        ("/api/ai/chat", lambda ids: {"prompt": "hi",
                                       "conversation_id": str(ids["conversation_id"])}),
        ("/api/ai/chat", lambda ids: {"prompt": "hi", "scene_id": str(ids["scene_id"])}),
    ],
)
async def test_ids_in_a_request_body_are_ownership_checked(session_factory, two_accounts,
                                                           path, body):
    """Attaching your codex entry to someone else's work is the same as editing it."""
    _alice, bob, ids = two_accounts
    async with _client_as(session_factory, bob) as ac:
        resp = await ac.post(path, json=body(ids))
    assert resp.status_code == 404, f"{path} accepted another account's ID: {resp.status_code}"


async def test_new_codex_entries_belong_to_their_creator(session_factory, two_accounts):
    """Entries made from the global codex page have no work; they must not vanish."""
    _alice, bob, _ids = two_accounts
    async with _client_as(session_factory, bob) as ac:
        created = await ac.post("/api/codex/", json={"name": "Bob's", "entry_type": "item"})
        assert created.status_code == 201, created.text
        listed = await ac.get("/api/codex/")
    assert [e["name"] for e in listed.json()] == ["Bob's"]
