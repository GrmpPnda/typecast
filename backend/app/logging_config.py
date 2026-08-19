"""Centralized logging configuration for Typecast."""

import logging
import os
import sys
from pathlib import Path


LOG_LEVEL = os.environ.get("TYPECAST_LOG_LEVEL", "INFO").upper()
LOG_FORMAT = os.environ.get(
    "TYPECAST_LOG_FORMAT",
    "%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
)
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_LOG_FILE = os.environ.get("TYPECAST_LOG_FILE", "")


def setup_logging() -> None:
    """Configure root logger with console and optional file output."""
    root = logging.getLogger()
    root.setLevel(LOG_LEVEL)

    if root.handlers:
        root.handlers.clear()

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(LOG_LEVEL)
    console.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT))
    root.addHandler(console)

    if _LOG_FILE:
        log_path = Path(_LOG_FILE)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(str(log_path))
        file_handler.setLevel(LOG_LEVEL)
        file_handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT))
        root.addHandler(file_handler)

    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.DEBUG if LOG_LEVEL == "DEBUG" else logging.WARNING
    )
