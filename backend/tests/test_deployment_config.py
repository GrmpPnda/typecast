"""The deployment files must agree with app/paths.py.

These are the deployment expression of the TYPECAST_DATA_DIR bug. docker-compose.yml
mounted a persistent volume at /app/data while backend/Dockerfile set no data dir, so
the database and uploads went to /app in the container's writable layer and were
discarded on every recreation, with the volume sitting empty. The healthcheck pointed
at /health, which has never been a route, so the container also reported permanently
unhealthy. Nothing in the test suite noticed either.
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

import pytest
import yaml

from app.config import Settings
from app.main import create_app

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
    return {route.path for route in create_app().routes if hasattr(route, "path")}


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
