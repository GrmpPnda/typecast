"""Every upload path must resolve through app.paths.

Ten modules used to compute their own backend-relative ``uploads`` directory. Under
a custom TYPECAST_DATA_DIR that made app/main.py serve /uploads from one place
while writes landed in another, so uploaded covers and images 404'd and were left
out of backups. The structural test below is the one that matters: it fails when a
new module reintroduces its own path calculation.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app import paths

APP_DIR = Path(paths.__file__).resolve().parent


def test_default_data_dir_is_the_backend_directory():
    assert paths.resolve_data_dir({}) == paths.BACKEND_DIR


def test_data_dir_honours_the_environment_variable():
    assert paths.resolve_data_dir({"TYPECAST_DATA_DIR": "/tmp/typecast-test"}) == Path(
        "/tmp/typecast-test"
    )


def test_empty_data_dir_falls_back_to_the_default():
    # An unset-but-present variable ("TYPECAST_DATA_DIR=") would otherwise
    # resolve to Path("") and put uploads in the working directory.
    assert paths.resolve_data_dir({"TYPECAST_DATA_DIR": ""}) == paths.BACKEND_DIR


def test_upload_dir_is_uploads_under_the_data_dir():
    env = {"TYPECAST_DATA_DIR": "/tmp/typecast-test"}
    assert paths.resolve_upload_dir(env) == Path("/tmp/typecast-test/uploads")


def test_db_path_sits_beside_the_uploads_directory():
    assert paths.DB_PATH.parent == paths.UPLOAD_DIR.parent == paths.DATA_DIR


@pytest.mark.parametrize(
    "module",
    [
        "app.api.codex",
        "app.api.fonts",
        "app.api.gallery",
        "app.api.images",
        "app.api.uploads",
        "app.services.backup",
        "app.services.cover",
        "app.services.export",
        "app.services.image_gen",
        "app.main",
    ],
)
def test_module_upload_dir_matches_the_shared_resolver(module):
    """Each module's UPLOAD_DIR is the shared one, not a private calculation."""
    mod = __import__(module, fromlist=["UPLOAD_DIR"])
    assert mod.UPLOAD_DIR == paths.UPLOAD_DIR


def _uploads_string_literals(tree: ast.AST) -> list[ast.Constant]:
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value == "uploads"
    ]


def test_no_module_builds_its_own_uploads_path():
    """Guards the fix: only app/paths.py may join a data dir to "uploads".

    The old pattern was ``Path(__file__).resolve().parent.parent.parent /
    "uploads"``. Anything that pairs a bare "uploads" literal with __file__ is
    computing a location app/main.py does not serve from.
    """
    offenders = []
    for source in sorted(APP_DIR.rglob("*.py")):
        if source.name == "paths.py":
            continue
        text = source.read_text()
        if "uploads" not in text:
            continue
        tree = ast.parse(text)
        if _uploads_string_literals(tree) and "__file__" in text:
            offenders.append(str(source.relative_to(APP_DIR.parent)))

    assert offenders == [], (
        "these modules compute their own uploads path instead of using "
        f"app.paths: {offenders}"
    )


def test_default_database_url_points_at_the_data_dir():
    """The DB must land in the same directory as the uploads.

    app/config.py's default was relative to the working directory, so launching
    the server from anywhere but backend/ split the two apart.
    """
    from app.config import _DEFAULT_DB_URL

    assert _DEFAULT_DB_URL.endswith(str(paths.DB_PATH))
    assert Path(_DEFAULT_DB_URL.split("///")[-1]).is_absolute()
