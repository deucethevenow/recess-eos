"""Sync observability: tracker + decorator that writes to eos_sync_runs.

Every sync subcommand in recess_os.py is wrapped by @sync_instrumented. The
decorator creates a SyncRunTracker, injects it into the Click context, runs
the subcommand, and writes the final status row to eos_sync_runs before
returning or re-raising any exception.

Subcommands call ctx.obj["instrumentation"].record_table_write(name, count)
whenever they write to a table. The tracker accumulates these and writes one
eos_sync_runs row per (run_id, table_name) at the end.
"""
from __future__ import annotations

import functools
import logging
import os
import subprocess
import traceback
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, List, Optional

logger = logging.getLogger("recess_os.sync")


def _git_sha() -> str:
    """Return the current git HEAD sha, or 'unknown' if unavailable."""
    try:
        return (
            subprocess.check_output(["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL)
            .decode()
            .strip()[:12]
        )
    except Exception:
        return os.environ.get("GIT_SHA", "unknown")


class SyncRunTracker:
    """Accumulates per-table row counts and writes them to eos_sync_runs at end."""

    TABLE_NAME = "eos_sync_runs"

    def __init__(self, bq_client: Any, cron_trigger: str = "manual") -> None:
        self.bq = bq_client
        self.run_id = uuid.uuid4().hex
        self.cron_trigger = cron_trigger
        self.git_sha = _git_sha()
        self.started_at: Optional[datetime] = None
        self.table_writes: List[dict] = []

    def start(self) -> None:
        """Record the run start -- writes the (run_id, 'ALL') row with status=running."""
        self.started_at = datetime.now(timezone.utc)
        logger.info("sync_run_started", extra={"run_id": self.run_id, "cron_trigger": self.cron_trigger})
        self._write_rows([
            {
                "run_id": self.run_id,
                "table_name": "ALL",
                "started_at": self.started_at.isoformat(),
                "ended_at": None,
                "status": "running",
                "row_count": 0,
                "duration_seconds": 0.0,
                "error_message": None,
                "git_sha": self.git_sha,
                "cron_trigger": self.cron_trigger,
            }
        ])

    def record_table_write(self, table_name: str, row_count: int) -> None:
        """Record that a particular table was written to during this run."""
        now = datetime.now(timezone.utc)
        duration = (now - self.started_at).total_seconds() if self.started_at else 0.0
        self.table_writes.append(
            {
                "run_id": self.run_id,
                "table_name": table_name,
                "started_at": self.started_at.isoformat() if self.started_at else now.isoformat(),
                "ended_at": now.isoformat(),
                "status": "success",
                "row_count": int(row_count),
                "duration_seconds": duration,
                "error_message": None,
                "git_sha": self.git_sha,
                "cron_trigger": self.cron_trigger,
            }
        )
        logger.info(
            "table_write_recorded",
            extra={"run_id": self.run_id, "table": table_name, "rows": row_count},
        )

    def finish(self, success: bool, error_message: Optional[str] = None) -> None:
        """Write the final (run_id, 'ALL') row with status=success|failed plus all per-table rows."""
        ended_at = datetime.now(timezone.utc)
        duration = (ended_at - self.started_at).total_seconds() if self.started_at else 0.0
        total_rows = sum(tw["row_count"] for tw in self.table_writes)

        final_rows = list(self.table_writes) + [
            {
                "run_id": self.run_id,
                "table_name": "ALL",
                "started_at": self.started_at.isoformat() if self.started_at else ended_at.isoformat(),
                "ended_at": ended_at.isoformat(),
                "status": "success" if success else "failed",
                "row_count": total_rows,
                "duration_seconds": duration,
                "error_message": error_message,
                "git_sha": self.git_sha,
                "cron_trigger": self.cron_trigger,
            }
        ]
        self._write_rows(final_rows)

        if success:
            logger.info("sync_run_succeeded", extra={"run_id": self.run_id, "total_rows": total_rows, "duration": duration})
        else:
            logger.error("sync_run_failed", extra={"run_id": self.run_id, "error": error_message, "duration": duration})

    def _write_rows(self, rows: List[dict]) -> None:
        """Write rows to eos_sync_runs via merge_events (idempotent on run_id+table_name)."""
        try:
            self.bq.merge_events(
                self.TABLE_NAME,
                rows,
                natural_key_columns=["run_id", "table_name"],
                run_id=self.run_id,
            )
        except Exception as e:
            # Never let observability writes crash the main sync
            logger.warning("eos_sync_runs_write_failed", extra={"error": str(e)})


def sync_instrumented(cron_trigger: str = "manual") -> Callable:
    """Decorator that wraps a sync subcommand with a SyncRunTracker.

    Usage:
        @cli.command("sync-to-bq")
        @click.pass_context
        @sync_instrumented(cron_trigger="cloud-scheduler")
        def sync_to_bq(ctx, ...):
            ctx.obj["instrumentation"].record_table_write("eos_projects", n)

    The decorator expects ctx.obj["bq_client"] to already be present (set up
    by the CLI group before subcommands run).
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(ctx: Any, *args: Any, **kwargs: Any) -> Any:
            bq = ctx.obj["bq_client"]
            tracker = SyncRunTracker(bq_client=bq, cron_trigger=cron_trigger)
            ctx.obj["instrumentation"] = tracker
            tracker.start()
            try:
                result = func(ctx, *args, **kwargs)
                tracker.finish(success=True)
                return result
            except Exception as e:
                tb = traceback.format_exc()
                tracker.finish(success=False, error_message=f"{type(e).__name__}: {e}\n{tb[:2000]}")
                raise
        return wrapper
    return decorator
