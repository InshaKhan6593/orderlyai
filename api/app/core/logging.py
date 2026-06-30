"""Minimal structured logging configuration."""
from __future__ import annotations

import logging
import sys


def configure_logging(debug: bool = False) -> None:
    level = logging.DEBUG if debug else logging.INFO
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    # LangSmith logs a DEBUG line every time it can't serialize a StructuredTool's Pydantic
    # args_schema for a trace (it falls back fine). Harmless, but it floods debug output and
    # buries the real agent/worker logs — keep it quiet regardless of the root level.
    logging.getLogger("langsmith").setLevel(logging.WARNING)
