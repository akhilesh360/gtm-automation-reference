"""Structured JSON logging with correlation IDs, plus the integration_log writer."""
from __future__ import annotations

import json
import logging
import sys
import uuid
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Iterator, Optional

import duckdb

from src.config import settings

STATUS_STARTED = "STARTED"
STATUS_SUCCESS = "SUCCESS"
STATUS_FAILED_VALIDATION = "FAILED_VALIDATION"
STATUS_FAILED_API = "FAILED_API"
STATUS_RETRYING = "RETRYING"
STATUS_RECONCILED = "RECONCILED"


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "level": record.levelname,
            "msg": record.getMessage(),
        }
        for key in ("workflow", "record_type", "record_id", "status", "correlation_id", "policy_version", "extra"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def get_logger(name: str = "gtm") -> logging.Logger:
    log = logging.getLogger(name)
    if log.handlers:
        return log
    log.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
    settings.log_file.parent.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(settings.log_file, encoding="utf-8")
    fh.setFormatter(JsonFormatter())
    sh = logging.StreamHandler(sys.stderr)
    sh.setFormatter(JsonFormatter())
    sh.setLevel(logging.WARNING)  # console shows only warnings/errors; the full JSON stream goes to the log file
    log.addHandler(fh)
    log.addHandler(sh)
    log.propagate = False
    return log


def new_correlation_id() -> str:
    return f"run-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"


def write_integration_log(con: duckdb.DuckDBPyConnection, workflow: str, status: str, correlation_id: str,
                          record_type: Optional[str] = None, record_id: Optional[str] = None,
                          started_at: Optional[datetime] = None, error: Optional[str] = None, retry_count: int = 0) -> str:
    log_id = f"LOG-{uuid.uuid4().hex[:10].upper()}"
    now = datetime.now()
    con.execute(
        "INSERT INTO integration_log VALUES (?,?,?,?,?,?,?,?,?,?)",
        [log_id, workflow, record_type, record_id, status, started_at or now,
         now if status != STATUS_STARTED else None, error, retry_count, correlation_id],
    )
    return log_id


@contextmanager
def workflow_run(con: duckdb.DuckDBPyConnection, workflow: str, correlation_id: str,
                 record_type: Optional[str] = None, record_id: Optional[str] = None) -> Iterator[dict]:
    """Writes STARTED, then SUCCESS or FAILED_* to integration_log around a block of work."""
    log = get_logger()
    started = datetime.now()
    ctx: dict[str, Any] = {"status": STATUS_SUCCESS, "error": None}
    write_integration_log(con, workflow, STATUS_STARTED, correlation_id, record_type, record_id, started)
    log.info("workflow started", extra={"workflow": workflow, "status": STATUS_STARTED, "correlation_id": correlation_id})
    try:
        yield ctx
    except Exception as e:  # noqa: BLE001
        ctx["status"] = ctx.get("failure_status") or STATUS_FAILED_API
        ctx["error"] = str(e)
        write_integration_log(con, workflow, ctx["status"], correlation_id, record_type, record_id, started, str(e))
        log.error("workflow failed", extra={"workflow": workflow, "status": ctx["status"], "correlation_id": correlation_id}, exc_info=True)
        raise
    else:
        write_integration_log(con, workflow, ctx["status"], correlation_id, record_type, record_id, started, ctx["error"])
        log.info("workflow finished", extra={"workflow": workflow, "status": ctx["status"], "correlation_id": correlation_id})
