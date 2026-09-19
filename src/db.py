"""DuckDB connection and SQL file runner with parameter substitution."""
from __future__ import annotations

import re
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import duckdb

from src.config import settings

_PARAM = re.compile(r"\$(\w+)")


def connect(path: Path | None = None) -> duckdb.DuckDBPyConnection:
    path = path or settings.duckdb_file
    path.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(path))


@contextmanager
def session(path: Path | None = None) -> Iterator[duckdb.DuckDBPyConnection]:
    con = connect(path)
    try:
        yield con
    finally:
        con.close()


def _substitute(sql: str, params: dict[str, Any]) -> str:
    def repl(m: re.Match) -> str:
        key = m.group(1)
        if key not in params:
            raise KeyError(f"SQL parameter ${key} not provided")
        v = params[key]
        if isinstance(v, str):
            return "'" + v.replace("'", "''") + "'"
        if isinstance(v, (list, tuple)):
            return "(" + ", ".join("'" + str(x).replace("'", "''") + "'" for x in v) + ")"
        return str(v)
    return _PARAM.sub(repl, sql)


def split_statements(sql: str) -> list[str]:
    """Split on ';' at end of statement, ignoring comments. Good enough for our own SQL files."""
    cleaned = "\n".join(line for line in sql.splitlines() if not line.strip().startswith("--"))
    return [s.strip() for s in cleaned.split(";") if s.strip()]


def run_sql_file(con: duckdb.DuckDBPyConnection, name: str, params: dict[str, Any] | None = None) -> None:
    path = settings.sql_dir / name
    sql = path.read_text(encoding="utf-8")
    if params:
        sql = _substitute(sql, params)
    for stmt in split_statements(sql):
        con.execute(stmt)


def read_sql_blocks(name: str) -> dict[str, str]:
    """Parse a SQL file with '-- name: <check_name>' headers into {name: sql}."""
    path = settings.sql_dir / name
    blocks: dict[str, str] = {}
    current: str | None = None
    buf: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"--\s*name:\s*(\w+)", line)
        if m:
            if current and buf:
                blocks[current] = "\n".join(buf).strip().rstrip(";")
            current, buf = m.group(1), []
        elif current is not None and not line.strip().startswith("--"):
            buf.append(line)
    if current and buf:
        blocks[current] = "\n".join(buf).strip().rstrip(";")
    return blocks
