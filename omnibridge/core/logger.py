"""Structured JSON logging to stderr.

stdout stays clean: for stdio MCP transport, stdout carries JSON-RPC only.
Log records may carry extra keywords (`log.info("x", extra={"tool": "file_read"})`)
which are merged into the JSON payload.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone

_RESERVED = {
    "args", "asctime", "created", "exc_info", "exc_text", "filename", "funcName", "levelname",
    "levelno", "lineno", "module", "msecs", "message", "msg", "name", "pathname", "process",
    "processName", "relativeCreated", "stack_info", "thread", "threadName", "taskName",
}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname.lower(),
            "msg": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                try:
                    json.dumps(value)
                    payload[key] = value
                except (TypeError, ValueError):
                    payload[key] = str(value)
        if record.exc_info:
            payload["error"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging() -> logging.Logger:
    """Idempotent: attach one JSON stderr handler and set the level from the environment."""
    logger = logging.getLogger("omnibridge")
    level = os.environ.get("OMNIBRIDGE_LOG_LEVEL", "INFO").upper()
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
        logger.propagate = False
    logger.setLevel(getattr(logging, level, logging.INFO))
    return logger


def get_logger(name: str = "omnibridge") -> logging.Logger:
    return setup_logging()


log = get_logger()
