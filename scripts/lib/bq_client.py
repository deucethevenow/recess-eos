"""BigQuery client wrapper for Recess OS.

Two sync primitives, matching the Truth Model:
- load_snapshot(): WRITE_TRUNCATE for snapshot tables (full replacement)
- merge_events():  MERGE WHEN NOT MATCHED THEN INSERT via per-run staging
                   (idempotent append for immutable event tables)

Both use load_table_from_json under the hood. insert_rows_json (streaming
inserts) is BANNED in this codebase — it's expensive, buffered, and does
not support MERGE.

This is the ONLY module in scripts/lib/ allowed to instantiate
google.cloud.bigquery.Client directly. A static test guard
(test_bq_access_policy.py) enforces this invariant.
"""
from __future__ import annotations

import logging
import os
from typing import Any, List, Optional

from google.cloud import bigquery

log = logging.getLogger(__name__)


class StagingCleanupError(Exception):
    """Raised in strict mode when staging table cleanup fails.

    Staging tables are named with a per-run UUID and have a 7-day TTL, so a
    failed delete is not data-destructive. But in strict mode we want to know
    about it immediately rather than accumulate orphans silently.
    """


class RecessOSBQClient:
    """Thin wrapper around google.cloud.bigquery that enforces the Recess OS Truth Model.

    Args:
        project_id: GCP project id.
        dataset: BigQuery dataset name.
        strict_cleanup: If True, a failed staging table cleanup raises
            StagingCleanupError instead of logging and continuing. Default False
            (warn-and-continue) because the 7-day TTL backstop makes cleanup
            failures non-fatal in production. Defaults from
            RECESS_OS_STRICT_BQ_CLEANUP environment variable when unset.
    """

    def __init__(self, project_id: str, dataset: str, strict_cleanup: Optional[bool] = None):
        self.project_id = project_id
        self.dataset = dataset
        self.bq = bigquery.Client(project=project_id)
        if strict_cleanup is None:
            strict_cleanup = os.environ.get("RECESS_OS_STRICT_BQ_CLEANUP", "").lower() in ("1", "true", "yes")
        self.strict_cleanup = strict_cleanup

    def full_table_id(self, table_name: str) -> str:
        """Return the fully qualified table id: project.dataset.table"""
        return f"{self.project_id}.{self.dataset}.{table_name}"

    def load_snapshot(
        self,
        table_name: str,
        rows: List[dict],
        schema: Optional[List[dict]] = None,
    ) -> int:
        """Atomically replace a snapshot table's contents.

        For snapshot tables only (eos_projects, eos_rocks, eos_goals).
        Uses WRITE_TRUNCATE — old rows are dropped atomically when the new
        load job commits. Retries are safe: two back-to-back runs with the
        same input produce identical final state.

        An empty rows list still dispatches a load job to CLEAR the table —
        "no projects" is a valid state.

        Args:
            table_name: Short table name (e.g. 'eos_projects').
            rows: List of dicts representing rows. May be empty.
            schema: Optional explicit schema (list of dicts with 'name'/'field_type').
                When provided, the load job uses this schema — required for tables
                that don't exist yet or where autodetect would be unreliable.
                When omitted, the existing table schema is used.

        Returns:
            Number of rows loaded.
        """
        job_config_kwargs: dict[str, Any] = dict(
            source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
            write_disposition="WRITE_TRUNCATE",
            autodetect=False,
        )
        if schema is not None:
            job_config_kwargs["schema"] = [bigquery.SchemaField(**s) for s in schema]

        job_config = bigquery.LoadJobConfig(**job_config_kwargs)
        # load_table_from_json handles [] by loading zero rows with WRITE_TRUNCATE,
        # which is exactly the desired "clear table" behavior.
        job = self.bq.load_table_from_json(
            rows,
            self.full_table_id(table_name),
            job_config=job_config,
        )
        job.result()  # wait for completion; raises on error
        return len(rows)

    def create_or_replace_view(self, view_name: str, sql: str) -> None:
        """Create or replace a BQ view with the given SQL.

        Uses delete-then-create because `bq mk --view --force` silently fails
        in some cases (see MEMORY.md BigQuery gotchas). This is the only
        view-management primitive in the canonical BQ layer — asana_eos_sync.py
        and any other writer must route through here.

        Args:
            view_name: Short view name (e.g. 'v_rock_health').
            sql: Full SELECT query for the view.
        """
        view_ref = self.full_table_id(view_name)
        # Delete first; not_found_ok=True so first-run is a no-op.
        self.bq.delete_table(view_ref, not_found_ok=True)
        view = bigquery.Table(view_ref)
        view.view_query = sql
        self.bq.create_table(view)

    def merge_events(
        self,
        table_name: str,
        rows: List[dict],
        natural_key_columns: List[str],
        run_id: str,
    ) -> int:
        """Idempotently append event rows via MERGE WHEN NOT MATCHED THEN INSERT.

        For event tables only (eos_status_updates, eos_l10_meetings,
        eos_l10_action_items, eos_goal_metric_history, eos_sync_runs).

        Event tables are IMMUTABLE in Recess OS: the MERGE contains ONLY
        ``WHEN NOT MATCHED THEN INSERT``. There is no ``WHEN MATCHED`` clause.
        If a row with the same natural key already exists, the new version
        is silently skipped. To "correct" an event, write a new row with
        later timestamp and filter in consumer views.

        Process:
          1. Upload rows to a per-run staging table keyed by run_id.
          2. MERGE staging INTO main on natural_key_columns.
          3. Delete the staging table.

        Args:
            table_name: Short name of the main event table.
            rows: Event rows to append. If empty, this is a no-op and hits nothing.
            natural_key_columns: Columns that uniquely identify an event (e.g.
                ['status_update_gid'] or ['asana_goal_id', 'pushed_at']).
            run_id: Per-sync UUID. Used to name the staging table so concurrent
                runs don't collide.

        Returns:
            Number of rows newly inserted (MERGE's num_dml_affected_rows).
        """
        if not rows:
            return 0

        # 1. Per-run staging table name (never collides across concurrent runs)
        staging_name = f"{table_name}_staging_{run_id.replace('-', '_')}"
        staging_full = self.full_table_id(staging_name)

        # Fetch schema from the main table so staging has identical column types.
        # This prevents autodetect from inferring STRING for null-only TIMESTAMP
        # columns (e.g. ended_at=None in start-row writes to eos_sync_runs).
        main_table = self.bq.get_table(self.full_table_id(table_name))
        load_config = bigquery.LoadJobConfig(
            source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
            write_disposition="WRITE_TRUNCATE",
            schema=main_table.schema,
        )
        load_job = self.bq.load_table_from_json(rows, staging_full, job_config=load_config)
        load_job.result()

        # 2. MERGE staging → main. WHEN NOT MATCHED THEN INSERT only.
        main_full = self.full_table_id(table_name)
        # Join condition: T.col1 = S.col1 AND T.col2 = S.col2 ...
        join_cond = " AND ".join(
            f"T.{col} = S.{col}" for col in natural_key_columns
        )
        # Column list for INSERT: derive from first row (all rows assumed to have same schema)
        columns = list(rows[0].keys())
        col_list = ", ".join(columns)
        val_list = ", ".join(f"S.{c}" for c in columns)
        merge_sql = f"""
        MERGE INTO `{main_full}` T
        USING `{staging_full}` S
        ON {join_cond}
        WHEN NOT MATCHED THEN INSERT ({col_list})
          VALUES ({val_list})
        """
        merge_job = self.bq.query(merge_sql)
        merge_job.result()
        inserted = merge_job.num_dml_affected_rows or 0

        # 3. Drop staging table.
        # The staging table has a 7-day TTL as a backstop, so a failed delete
        # is not data-destructive. But we log structured info so orphans don't
        # accumulate silently. In strict_cleanup mode, raise instead.
        try:
            self.bq.delete_table(staging_full, not_found_ok=True)
        except Exception as e:
            log.warning(
                "bq_staging_cleanup_failed",
                extra={
                    "run_id": run_id,
                    "table": table_name,
                    "staging_table": staging_full,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "backstop": "7-day TTL will reclaim orphan",
                },
            )
            if self.strict_cleanup:
                raise StagingCleanupError(
                    f"Failed to delete staging table {staging_full} for run {run_id}: "
                    f"{type(e).__name__}: {e}"
                ) from e

        return int(inserted)

    def query(self, sql: str) -> List[dict]:
        """Run a query and return rows as a list of dicts."""
        results = self.bq.query(sql).result()
        return [dict(row.items()) for row in results]
