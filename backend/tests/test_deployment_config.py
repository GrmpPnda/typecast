"""The deployment files must agree with app/paths.py.

These are the deployment expression of the TYPECAST_DATA_DIR bug. docker-compose.yml
mounted a persistent volume at /app/data while backend/Dockerfile set no data dir, so
the database and uploads went to /app in the container's writable layer and were
discarded on every recreation, with the volume sitting empty. The healthcheck pointed
at /health, which has never been a route, so the container also reported permanently
unhealthy. Nothing in the test suite noticed either.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from urllib.parse import urlparse

import pytest
import yaml

from app.config import Settings
from app.main import create_app
from tests.routes import api_routes, mounted_paths

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = REPO_ROOT / "docker-compose.yml"
BACKEND_DOCKERFILE = REPO_ROOT / "backend" / "Dockerfile"
ROOT_DOCKERFILE = REPO_ROOT / "Dockerfile"
ENV_EXAMPLE = REPO_ROOT / ".env.example"


def _compose() -> dict:
    return yaml.safe_load(COMPOSE_FILE.read_text())


def _dockerfile_env(path: Path) -> dict[str, str]:
    """The ENV assignments in a Dockerfile, single-variable form only."""
    found = {}
    for line in path.read_text().splitlines():
        match = re.match(r"^\s*ENV\s+([A-Z_][A-Z0-9_]*)\s*[=\s]\s*(\S+)\s*$", line)
        if match:
            found[match.group(1)] = match.group(2)
    return found


def _app_route_paths() -> set[str]:
    return {path for _method, path, _route in api_routes(create_app())}


def _healthcheck_paths(text: str) -> list[str]:
    return [urlparse(url).path for url in re.findall(r"https?://\S+", text)]


def test_compose_data_dir_matches_the_persistent_volume():
    """The data dir must be the mount point, or manuscripts die with the container."""
    backend = _compose()["services"]["backend"]
    data_dir = backend["environment"]["TYPECAST_DATA_DIR"]
    mounts = {m.split(":")[1] for m in backend["volumes"] if m.startswith("typecast-data:")}
    assert mounts == {data_dir}, (
        f"typecast-data is mounted at {mounts} but the app writes to {data_dir}; "
        "anything written would be lost when the container is recreated"
    )


def test_backend_dockerfile_sets_the_same_data_dir_as_compose():
    """The image alone must be correct, not only when compose supplies the variable."""
    compose_dir = _compose()["services"]["backend"]["environment"]["TYPECAST_DATA_DIR"]
    assert _dockerfile_env(BACKEND_DOCKERFILE).get("TYPECAST_DATA_DIR") == compose_dir


def test_compose_builds_the_backend_dockerfile():
    """Guards the two tests above: they only mean something if compose builds this image."""
    build = _compose()["services"]["backend"]["build"]
    assert (REPO_ROOT / build["context"] / build["dockerfile"]).resolve() == BACKEND_DOCKERFILE


def test_root_dockerfile_data_dir_is_absolute():
    data_dir = _dockerfile_env(ROOT_DOCKERFILE).get("TYPECAST_DATA_DIR")
    assert data_dir and Path(data_dir).is_absolute()


@pytest.mark.parametrize(
    "source",
    [
        pytest.param("compose", id="docker-compose.yml"),
        pytest.param("dockerfile", id="Dockerfile"),
    ],
)
def test_healthcheck_targets_a_real_route(source):
    """A healthcheck on a nonexistent path reports the container unhealthy forever."""
    if source == "compose":
        text = " ".join(_compose()["services"]["backend"]["healthcheck"]["test"])
    else:
        text = ROOT_DOCKERFILE.read_text()

    checked = _healthcheck_paths(text)
    assert checked, f"no healthcheck URL found in {source}"
    routes = _app_route_paths()
    assert [p for p in checked if p not in routes] == []


def test_nginx_proxies_every_path_the_backend_serves():
    """The compose frontend is nginx, so anything it does not proxy 404s.

    ``/uploads`` was missing: the backend hands out absolute "/uploads/..."
    paths from a StaticFiles mount, and the Vite dev server proxies that prefix,
    so every cover, gallery image, codex image, and custom font worked in
    development and broke in the container.
    """
    nginx = (REPO_ROOT / "frontend" / "nginx.conf").read_text()
    proxied = set(re.findall(r"location\s+(/[a-z]+)/\s*\{[^}]*proxy_pass", nginx, re.S))

    app = create_app()
    # Mounts, plus every top-level prefix with routes (/api, and /uploads since it
    # stopped being a public mount).
    served = mounted_paths(app) | {
        "/" + path.split("/")[1] for _, path, _ in api_routes(app) if path.count("/") > 1
    }
    assert "/uploads" in served

    missing = sorted(served - proxied)
    assert missing == [], (
        f"nginx.conf does not proxy {missing}; requests to those paths will be "
        "answered by the SPA fallback instead of the backend."
    )


def test_nginx_forwards_the_host_with_its_port():
    """``$host`` drops the port; the backend builds redirects from what it gets.

    With ``$host`` every trailing-slash redirect pointed at port 80, so behind
    nginx on any other port the browser's follow-up request went nowhere. The
    library, codex, and every create call failed, and an empty library looked
    exactly like a working one with no data.
    """
    nginx = (REPO_ROOT / "frontend" / "nginx.conf").read_text()
    hosts = re.findall(r"proxy_set_header\s+Host\s+(\$\w+);", nginx)
    assert hosts, "nginx.conf must set the Host header for proxied requests"
    assert set(hosts) == {"$http_host"}, f"use $http_host, not {sorted(set(hosts))}"
    assert "X-Forwarded-Proto $scheme" not in nginx, (
        "overwriting X-Forwarded-Proto with this hop's scheme turns an upstream "
        "https into http"
    )


def test_frontend_never_relies_on_a_trailing_slash_redirect():
    """Calls must hit the canonical URL, so no proxy can break them.

    A route registered as "/" on a router mounted at "/api/works" lives at
    "/api/works/"; calling "/works" costs a 307 whose Location depends on every
    proxy in between forwarding the host correctly.
    """
    root_routes = {
        path[len("/api") : -1]
        for _method, path, _route in api_routes(create_app())
        if path.startswith("/api/") and path.endswith("/")
    }
    root_routes.discard("")

    call = re.compile(
        r"client\.(?:get|post|put|patch|delete)(?:<[^>]*>)?\(\s*[\"'`](/[^\"'`?$]*)"
    )
    offenders = []
    for source in sorted((REPO_ROOT / "frontend" / "src").rglob("*.ts*")):
        for lineno, line in enumerate(source.read_text().splitlines(), 1):
            for path in call.findall(line):
                if path in root_routes:
                    rel = source.relative_to(REPO_ROOT)
                    offenders.append(f"{rel}:{lineno} calls {path!r}, should be {path + '/'!r}")
    assert offenders == [], "\n".join(offenders)


def test_nginx_accepts_bodies_larger_than_its_default():
    """Cover images, fonts, and backup restores all exceed nginx's 1m default."""
    nginx = (REPO_ROOT / "frontend" / "nginx.conf").read_text()
    match = re.search(r"client_max_body_size\s+(\d+)([kmg])", nginx, re.I)
    assert match, "nginx.conf must raise client_max_body_size above the 1m default"
    size, unit = int(match.group(1)), match.group(2).lower()
    megabytes = size * {"k": 1 / 1024, "m": 1, "g": 1024}[unit]
    assert megabytes >= 50, f"client_max_body_size is only {megabytes}m"


def test_every_third_party_import_is_a_declared_dependency():
    """A container installs from pyproject.toml and nothing else.

    ``cryptography`` was imported by app/services/crypto.py but never declared,
    so every image built from this file died at import with ModuleNotFoundError
    while a developer machine that happened to have it installed worked fine.
    Relying on a transitive dependency is the same bug waiting to happen: the
    package that supplies it can drop it in any release.
    """
    import sys
    import tomllib

    # Import name differs from the distribution name for these.
    distribution_of = {
        "PIL": "pillow",
        "bs4": "beautifulsoup4",
        "docx": "python-docx",
        "dotenv": "python-dotenv",
        "fontTools": "fonttools",
        "jose": "python-jose",
        "jwt": "pyjwt",
        "multipart": "python-multipart",
        "pydantic_settings": "pydantic-settings",
        "yaml": "pyyaml",
    }

    imported: set[str] = set()
    for source in (REPO_ROOT / "backend" / "app").rglob("*.py"):
        for node in ast.walk(ast.parse(source.read_text())):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                imported.add(node.module.split(".")[0])

    project = tomllib.loads((REPO_ROOT / "backend" / "pyproject.toml").read_text())["project"]
    # Only what a deployment installs counts. The image runs ".[postgres]", so a
    # runtime import satisfied solely by [dev] is still missing in production:
    # that is exactly how httpx, which every Google Drive call goes through,
    # ended up absent from the container while the test suite passed.
    extras = project.get("optional-dependencies", {})
    specs = list(project["dependencies"]) + list(extras.get("postgres", []))
    declared = {
        spec.split(">")[0].split("<")[0].split("[")[0].split("=")[0].strip().lower()
        for spec in specs
    }

    undeclared = sorted(
        name
        for name in imported
        if name not in sys.stdlib_module_names
        and name != "app"
        and distribution_of.get(name, name).lower() not in declared
    )
    assert undeclared == [], (
        f"imported but not declared in pyproject.toml: {undeclared}. "
        "The app will fail at import inside a container."
    )


def test_env_example_is_loadable_as_a_dotenv():
    """Settings forbids extra keys, so a stale key in the template is a startup crash.

    The template shipped CONTENT_DIR and CODEX_DIR, which no code has ever read.
    Copying it to backend/.env raised extra_forbidden before the app could start.
    """
    keys = {
        line.split("=", 1)[0].strip()
        for line in ENV_EXAMPLE.read_text().splitlines()
        if "=" in line and not line.lstrip().startswith("#")
    }
    unknown = sorted(
        k for k in keys if k not in Settings.model_fields and not k.startswith("TYPECAST_")
    )
    assert unknown == [], f".env.example sets keys the backend rejects: {unknown}"


# --- TLS -----------------------------------------------------------------------------


def _nginx_servers() -> list[str]:
    """The text of each top-level server block in nginx.conf."""
    text = (REPO_ROOT / "frontend" / "nginx.conf").read_text()
    blocks, depth, start = [], 0, None
    for match in re.finditer(r"server\s*\{|\{|\}", text):
        token = match.group(0)
        if token.startswith("server") and depth == 0:
            start, depth = match.start(), 1
        elif token == "{" and start is not None:
            depth += 1
        elif token == "}" and start is not None:
            depth -= 1
            if depth == 0:
                blocks.append(text[start : match.end()])
                start = None
    return blocks


def test_nginx_serves_the_app_only_over_tls():
    servers = _nginx_servers()
    tls = [s for s in servers if re.search(r"listen\s+443\s+ssl", s)]
    plain = [s for s in servers if re.search(r"listen\s+80\b", s)]
    assert len(tls) == 1, "exactly one TLS server block"
    assert "ssl_certificate " in tls[0] and "ssl_certificate_key" in tls[0]
    assert "TLSv1.2 TLSv1.3" in tls[0], "only TLS 1.2 and 1.3"
    assert "proxy_pass" in tls[0], "the app is served from the TLS server"
    # Plain HTTP must only redirect; serving anything there defeats the point.
    assert len(plain) == 1 and "proxy_pass" not in plain[0]
    assert re.search(r"return\s+301\s+https://", plain[0])


def test_nginx_does_not_send_hsts():
    """Over an SSH tunnel the host is "localhost": a trusted self-signed cert plus
    HSTS would force HTTPS on every localhost port, breaking plain-HTTP dev servers."""
    nginx = (REPO_ROOT / "frontend" / "nginx.conf").read_text()
    assert not re.search(r"add_header\s+Strict-Transport-Security", nginx)


def test_compose_publishes_only_the_tls_frontend():
    """A published backend port bypasses TLS and lets clients spoof X-Forwarded-*,
    which uvicorn trusts because it runs with --forwarded-allow-ips."""
    services = _compose()["services"]
    assert "ports" not in services["backend"], "the backend must not be published"
    published = " ".join(services["frontend"]["ports"])
    assert ":443" in published
    assert any(":/etc/nginx/certs" in v for v in services["frontend"]["volumes"])


def test_the_frontend_image_can_make_its_own_certificate():
    dockerfile = (REPO_ROOT / "frontend" / "Dockerfile").read_text()
    script = REPO_ROOT / "frontend" / "docker-entrypoint.d" / "40-typecast-tls.sh"
    assert "apk add --no-cache openssl" in dockerfile, "nginx:alpine has no openssl"
    assert "/etc/nginx/templates/default.conf.template" in dockerfile, (
        "nginx.conf must be a template so ${TYPECAST_HTTPS_PORT} is substituted"
    )
    assert "40-typecast-tls.sh" in dockerfile
    text = script.read_text()
    assert "subjectAltName" in text, "browsers ignore CN; the name must be in a SAN"
    assert script.stat().st_mode & 0o111, "entrypoint scripts must be executable"


@pytest.mark.parametrize("scheme", ["http", "https"])
async def test_force_https_redirects_except_for_health_probes(monkeypatch, scheme):
    from httpx import ASGITransport, AsyncClient

    import app.main as main_module

    monkeypatch.setattr(main_module, "FORCE_HTTPS", True)
    application = main_module.create_app()
    async with AsyncClient(
        transport=ASGITransport(app=application), base_url=f"{scheme}://typecast.example"
    ) as ac:
        page = await ac.get("/api/auth/mode")
        health = await ac.get("/api/health")

    assert health.status_code == 200, "probes arrive over plain HTTP and must not bounce"
    if scheme == "http":
        assert page.status_code == 308, "308 keeps the method, so a POST stays a POST"
        assert page.headers["location"].startswith("https://typecast.example/")
        assert "strict-transport-security" not in page.headers
    else:
        assert page.status_code == 200
        assert "max-age=" in page.headers["strict-transport-security"]


async def test_the_single_container_image_serves_frontend_routes(tmp_path, monkeypatch):
    """A refresh or bookmark of /settings must load the app, not a JSON 404.

    Plain StaticFiles had no fallback. Azure runs this image, so every deep link
    and every refresh off the home page was broken there.
    """
    from httpx import ASGITransport, AsyncClient

    import app.main as main_module

    (tmp_path / "index.html").write_text("<html>typecast spa</html>")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("console.log(1)")
    monkeypatch.setattr(main_module, "STATIC_DIR", tmp_path)

    application = main_module.create_app()
    async with AsyncClient(transport=ASGITransport(app=application), base_url="http://t") as ac:
        for route in ("/", "/settings", "/work/123/chapter/456"):
            resp = await ac.get(route)
            assert resp.status_code == 200 and "typecast spa" in resp.text, route
        assert (await ac.get("/assets/app.js")).text == "console.log(1)"
        missing_asset = await ac.get("/assets/missing.js")
        assert missing_asset.status_code == 200, "unknown non-API paths fall back"
        for api_typo in ("/api/nope", "/uploads/nope.png"):
            resp = await ac.get(api_typo)
            assert resp.status_code == 404, f"{api_typo} must not be answered with a page"


@pytest.mark.parametrize(
    "origins",
    [
        [],  # the default: same-origin only
        ["https://typecast.example"],  # an explicit list that does not include the attacker
        ["*"],  # a wildcard, which must never be combined with credentials
    ],
    ids=["default", "explicit-list", "wildcard"],
)
async def test_other_websites_cannot_read_the_api_with_your_cookies(monkeypatch, origins):
    """Under single sign-on the session is a cookie, so a credentialed wildcard is a
    cross-site read of everything: Starlette echoed any Origin and sent
    Allow-Credentials whenever the request carried a cookie.

    A browser lets a page read a cross-origin response sent with cookies only if
    Allow-Origin names that page's origin exactly and Allow-Credentials is true.
    """
    from httpx import ASGITransport, AsyncClient

    import app.main as main_module

    monkeypatch.setattr(main_module, "CORS_ORIGINS", origins)
    application = main_module.create_app()
    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="https://typecast.example"
    ) as ac:
        resp = await ac.get(
            "/api/health",
            headers={"Origin": "https://evil.example", "Cookie": "AppServiceAuthSession=x"},
        )
    allow_origin = resp.headers.get("access-control-allow-origin")
    credentials = resp.headers.get("access-control-allow-credentials")
    readable_with_cookies = allow_origin == "https://evil.example" and credentials == "true"
    assert not readable_with_cookies, (allow_origin, credentials)
    if allow_origin == "*":
        assert credentials != "true"


def test_every_install_path_uses_the_lock():
    """CI, the Azure image, and the compose image must install the same versions.

    Without the lock, the image built from whatever was newest on the day. That
    shipped FastAPI 0.143 while every test had run on 0.136, and 0.143 changed
    how routes are stored in a way that refused owners their own codex images.
    """
    sources = {
        "Dockerfile": (REPO_ROOT / "Dockerfile").read_text(),
        "backend/Dockerfile": BACKEND_DOCKERFILE.read_text(),
        ".github/workflows/ci.yml": (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(),
    }
    for name, text in sources.items():
        installs = [line for line in text.splitlines() if "pip install" in line and "." in line]
        assert installs, f"{name}: no pip install of the project found"
        unlocked = [line.strip() for line in installs if "-c requirements.lock" not in line]
        assert unlocked == [], f"{name} installs without the lock: {unlocked}"


def test_the_lock_covers_every_declared_dependency():
    """A dependency added to pyproject.toml but not locked installs at its newest.

    Constraints only pin what they list, so a gap here is silent.
    """
    import tomllib

    lock = (REPO_ROOT / "backend" / "requirements.lock").read_text().lower()
    locked = {
        line.split("==")[0].strip().replace("_", "-")
        for line in lock.splitlines()
        if "==" in line and not line.startswith("#")
    }
    project = tomllib.loads((REPO_ROOT / "backend" / "pyproject.toml").read_text())["project"]
    specs = list(project["dependencies"])
    for group in project.get("optional-dependencies", {}).values():
        specs.extend(group)
    declared = {
        re.split(r"[<>=!~\[ ]", spec, maxsplit=1)[0].strip().lower().replace("_", "-")
        for spec in specs
    }
    missing = sorted(declared - locked)
    assert missing == [], (
        f"declared but not locked: {missing}. Run backend/scripts/lock-deps.sh"
    )
