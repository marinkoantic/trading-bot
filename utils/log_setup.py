"""Structured logging: JSON lines to a rotating file, concise text to stderr.

Each record carries UTC time, level, logger (module), message and - when
passed via ``extra`` - ``run_id``, ``symbol`` and ``order_id``. A redaction
filter masks anything that looks like a credential before it is written.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

_CONTEXT_FIELDS = ("run_id", "symbol", "order_id")
_SECRET_RE = re.compile(r"(?i)(api[_-]?key|secret|password|token|signature)(\s*[=:]\s*)([^\s,&\"']+)")


def redact(text: str) -> str:
    return _SECRET_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}***", text)


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.getMessage())
        record.args = ()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for name in _CONTEXT_FIELDS:
            value = getattr(record, name, None)
            if value not in (None, "-"):
                payload[name] = value
        if record.exc_info:
            payload["exc"] = redact(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(log_dir: str | Path, level: str = "INFO", console: bool = True) -> Path:
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / "tradingbot.jsonl"
    root = logging.getLogger()
    root.setLevel(level)
    for handler in list(root.handlers):
        if getattr(handler, "_tradingbot", False):
            root.removeHandler(handler)
            handler.close()
    file_handler = RotatingFileHandler(path, maxBytes=10_000_000, backupCount=5, encoding="utf-8")
    file_handler.setFormatter(JsonFormatter())
    file_handler.addFilter(RedactingFilter())
    file_handler._tradingbot = True  # type: ignore[attr-defined]
    root.addHandler(file_handler)
    if console:
        stream = logging.StreamHandler()
        stream.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%H:%M:%S"))
        stream.addFilter(RedactingFilter())
        stream.setLevel(logging.WARNING if level == "INFO" else level)
        stream._tradingbot = True  # type: ignore[attr-defined]
        root.addHandler(stream)
    return path
