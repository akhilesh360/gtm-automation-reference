"""Console alert summary. A Slack/email hook would plug in here."""
from __future__ import annotations

import duckdb

from src.monitoring.quality_checks import DqResult


def summarize(con: duckdb.DuckDBPyConnection, dq: list[DqResult]) -> str:
    lines = ["=== GTM automation alert summary ==="]
    errors = [r for r in dq if r.severity == "error" and r.row_count > 0]
    warns = [r for r in dq if r.severity == "warn" and r.row_count > 0]
    lines.append(f"Data quality: {len(errors)} error check(s), {len(warns)} warning check(s)")
    for r in errors:
        lines.append(f"  ERROR {r.check_name}: {r.row_count} rows (e.g. {', '.join(r.sample_ids)})")
    for r in warns:
        lines.append(f"  WARN  {r.check_name}: {r.row_count} rows (e.g. {', '.join(r.sample_ids)})")
    failed = con.execute(
        "SELECT workflow_name, COUNT(*) FROM integration_log WHERE status IN ('FAILED_VALIDATION','FAILED_API') "
        "AND started_at >= CURRENT_TIMESTAMP - INTERVAL 24 HOUR GROUP BY 1"
    ).fetchall()
    lines.append(f"Failed integration runs (24h): {sum(n for _, n in failed)}")
    for wf, n in failed:
        lines.append(f"  {wf}: {n}")
    return "\n".join(lines)
