"""Recess OS — One module, every system action.

Usage:
    recess_os sync-to-bq           # Asana → BQ daily sync (8am ET)
    recess_os push-kpi-goals       # BQ → Asana Goals (Friday)
    recess_os monday-pulse         # Slack post to #recess-goals-kpis (Monday)
    recess_os update-all-hands-deck  # Slides metric update (Monday, bi-weekly)

Each subcommand reads config/recess_os.yml and
sources credentials from ~/Projects/daily-brief-agent/.env.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date
from pathlib import Path

import click

from lib.config import load_config
from lib.orchestrator import (
    ConsumerResult,
    SnapshotUnavailableError,
    build_all_payloads,
    fetch_latest_snapshot,
)
from lib.run_audit import (
    DeliveryAuditEntry,
    MetricRun,
    generate_run_id,
    payload_to_audit_entry,
    record_deliveries,
    record_run,
)


DEFAULT_CONFIG = Path(__file__).parent.parent / "config" / "recess_os.yml"
SLACK_CHANNEL = "C0AQP3WH7AB"  # #recess-goals-kpis


def _get_bq_client(ctx):
    """Lazily create and cache BQ client in ctx.obj."""
    if "bq_client" not in ctx.obj:
        from lib.bq_client import RecessOSBQClient

        bq_config = ctx.obj["config"]["bigquery"]
        ctx.obj["bq_client"] = RecessOSBQClient(
            project_id=bq_config["project_id"],
            dataset=bq_config["dataset"],
        )
    return ctx.obj["bq_client"]


def _consumer_results_to_audit_entries(
    results: list[ConsumerResult],
    all_payloads: dict,
    run_id: str,
    command: str,
) -> list[DeliveryAuditEntry]:
    """Convert ConsumerResult list → DeliveryAuditEntry list.

    Matches results to payloads by (registry_key, dept_id) for full audit data.
    Generic — no per-consumer logic.
    """
    # Build lookup: (registry_key, dept_id) → MetricPayload
    payload_lookup = {}
    for dept_id, payloads in all_payloads.items():
        for p in payloads:
            payload_lookup[(p.registry_key, dept_id)] = p

    entries = []
    for cr in results:
        payload = payload_lookup.get((cr.registry_key, cr.dept_id))
        if not payload:
            raise AssertionError(
                f"Orphaned ConsumerResult: registry_key={cr.registry_key!r}, "
                f"dept_id={cr.dept_id!r}, consumer={cr.consumer!r} — "
                f"no matching payload found. This is a bug in the consumer."
            )
        entries.append(payload_to_audit_entry(
            run_id=run_id,
            command=command,
            payload=payload,
            consumer=cr.consumer,
            action=cr.action,
            error=cr.error_message,
        ))
    return entries


def _run_phase2_command(ctx, command_name, dry_run, consumer_fn):
    """6-step orchestration for all Phase 2 subcommands.

    1. Generate run_id, start MetricRun
    2. Fetch snapshot (abort on SnapshotUnavailableError → error MetricRun)
    3. Build all payloads ONCE via build_all_payloads()
    4. Call consumer_fn(all_payloads, snapshot_ts, config, dry_run)
       → (side_effect_data, list[ConsumerResult])
    5. Map ConsumerResult → DeliveryAuditEntry (generic, no per-consumer logic)
    6. record_deliveries() + run.complete() + record_run()
    """
    bq_client = _get_bq_client(ctx)
    config = ctx.obj["config"]
    run_id = generate_run_id()
    run = MetricRun(run_id=run_id, command=command_name).start()

    # Step 2: Fetch snapshot
    try:
        snapshot_row, snapshot_ts = fetch_latest_snapshot(bq_client)
    except SnapshotUnavailableError as e:
        run.complete(error=str(e))
        record_run(bq_client, run)
        click.echo(f"ERROR: {e}", err=True)
        sys.exit(1)

    # Step 3: Build payloads ONCE
    all_payloads = build_all_payloads(config, snapshot_row, snapshot_ts)

    # Step 4: Consumer function
    try:
        side_effect_data, consumer_results = consumer_fn(
            all_payloads, snapshot_ts, config, dry_run
        )
    except Exception as e:
        run.complete(error=f"Consumer error: {e}", snapshot_timestamp=snapshot_ts)
        record_run(bq_client, run)
        click.echo(f"ERROR in {command_name}: {e}", err=True)
        sys.exit(1)

    # Step 5: Map results → audit entries
    audit_entries = _consumer_results_to_audit_entries(
        consumer_results, all_payloads, run_id, command_name,
    )

    # Step 6: Record audit + complete run
    record_deliveries(bq_client, audit_entries, run_id)
    run.complete(
        deliveries=audit_entries,
        snapshot_timestamp=snapshot_ts,
    )
    record_run(bq_client, run)

    click.echo(
        f"{command_name}: {run.status} — "
        f"{len(consumer_results)} metrics, run_id={run_id}"
    )

    return side_effect_data, consumer_results


@click.group()
@click.option(
    "--config",
    default=str(DEFAULT_CONFIG),
    help="Path to recess_os.yml config file.",
)
@click.pass_context
def cli(ctx, config):
    """Recess OS — Automate the EOS rhythm."""
    ctx.ensure_object(dict)
    ctx.obj["config"] = load_config(Path(config))


@cli.command("sync-to-bq")
@click.option("--portfolio", required=True, help="Asana portfolio GID to sync from.")
@click.option(
    "--cron-trigger",
    default="manual",
    help="How this run was triggered: 'cloud-scheduler', 'manual', 'backfill', 'test'",
)
@click.pass_context
def sync_to_bq(ctx, portfolio, cron_trigger):
    """Sync Asana data into BigQuery (App_Recess_OS dataset)."""
    from lib.asana_client import RecessAsanaClient
    from lib.bq_client import RecessOSBQClient
    from lib.instrumentation import sync_instrumented
    from lib.sync_projects import sync_projects_to_bq

    config = ctx.obj["config"]
    bq_config = config["bigquery"]

    asana = RecessAsanaClient(workspace_gid="21487286163067")
    bq = RecessOSBQClient(
        project_id=bq_config["project_id"],
        dataset=bq_config["dataset"],
    )
    ctx.obj["bq_client"] = bq

    @sync_instrumented(cron_trigger=cron_trigger)
    def _run(ctx):
        n_projects = sync_projects_to_bq(asana, bq, portfolio_gid=portfolio)
        ctx.obj["instrumentation"].record_table_write("eos_projects", n_projects)
        click.echo(f"sync-to-bq: synced {n_projects} projects to App_Recess_OS.eos_projects")

    _run(ctx)


@cli.command("push-kpi-goals")
@click.option("--dry-run", is_flag=True, help="Log actions without touching Asana.")
@click.option("--allow-stale", is_flag=True, help="Push even if snapshot is stale.")
@click.pass_context
def push_kpi_goals_cmd(ctx, dry_run, allow_stale):
    """Push BQ KPI values into Asana Goal metrics (Friday cron)."""
    from lib.kpi_goals_pusher import push_kpi_goals

    def _consumer(all_payloads, snapshot_ts, config, dry_run):
        goal_configs = config.get("goals", [])
        # Flatten payloads to a single list for the goals pusher
        all_flat = [p for dept in all_payloads.values() for p in dept]

        # Match payloads to goal configs by registry_key
        matched_payloads = []
        matched_goals = []
        stale_skipped = []  # track stale skips for audit
        for goal in goal_configs:
            rk = goal.get("registry_key")
            if rk is None:
                continue
            for p in all_flat:
                if p.registry_key == rk:
                    # Stale check (C2): skip stale unless --allow-stale
                    if p.availability_state == "stale" and not allow_stale:
                        stale_skipped.append((goal, p))
                        break
                    matched_payloads.append(p)
                    matched_goals.append(goal)
                    break

        from lib.asana_client import RecessAsanaClient
        asana = RecessAsanaClient(workspace_gid="21487286163067")
        bq_client = _get_bq_client(ctx)

        results = push_kpi_goals(
            payloads=matched_payloads,
            goal_configs=matched_goals,
            asana_client=asana,
            bq_client=bq_client,
            dry_run=dry_run,
            run_id=None,
        )

        # Convert PushResult → ConsumerResult
        # Use matched payload's dept_id (not "goals") so audit lookup matches
        consumer_results = []
        for pr, goal, payload in zip(results, matched_goals, matched_payloads):
            consumer_results.append(ConsumerResult(
                registry_key=goal.get("registry_key", ""),
                dept_id=payload.dept_id,
                consumer="asana_goal",
                action=pr.action,
                error_message=pr.reason if pr.action == "error" else None,
            ))

        # Emit audit records for stale-skipped goals (C2 enforcement)
        for goal, payload in stale_skipped:
            consumer_results.append(ConsumerResult(
                registry_key=goal.get("registry_key", ""),
                dept_id=payload.dept_id,
                consumer="asana_goal",
                action="skipped",
                error_message="stale_data_skipped",
            ))

        return results, consumer_results

    _run_phase2_command(ctx, "push-kpi-goals", dry_run, _consumer)


@cli.command("monday-pulse")
@click.option("--dry-run", is_flag=True, help="Render but don't post to Slack.")
@click.pass_context
def monday_pulse_cmd(ctx, dry_run):
    """Post Monday morning KPI pulse to #recess-goals-kpis Slack channel."""
    from lib.monday_pulse import post_monday_pulse, render_monday_pulse

    def _consumer(all_payloads, snapshot_ts, config, dry_run):
        meetings = config.get("meetings", [])

        # Fetch project/Rock progress from BQ for the portfolio section
        bq_client = _get_bq_client(ctx)
        try:
            project_data = bq_client.query(
                "SELECT name, owner_name, status, completion_percent, task_count "
                "FROM `" + bq_client.full_table_id("eos_projects") + "` "
                "ORDER BY name"
            )
        except Exception as e:
            click.echo(f"WARNING: Failed to fetch project data: {e}", err=True)
            project_data = []

        blocks, results = render_monday_pulse(
            all_payloads, snapshot_ts, meetings, project_data=project_data,
        )

        if dry_run:
            click.echo(json.dumps(blocks, indent=2))
            return blocks, results

        slack_token = os.environ.get("SLACK_BOT_TOKEN", "")
        if not slack_token:
            # Try loading from daily-brief-agent/.env
            env_path = Path.home() / "Projects" / "daily-brief-agent" / ".env"
            if env_path.exists():
                for line in env_path.read_text().splitlines():
                    if line.startswith("SLACK_BOT_TOKEN="):
                        slack_token = line.split("=", 1)[1].strip().strip('"')
                        break

        if not slack_token:
            raise RuntimeError(
                "SLACK_BOT_TOKEN not found in environment or "
                "~/Projects/daily-brief-agent/.env. Cannot post Monday Pulse."
            )

        ts = post_monday_pulse(blocks, SLACK_CHANNEL, slack_token, dry_run=False)
        click.echo(f"Posted Monday Pulse to {SLACK_CHANNEL}, ts={ts}")
        return ts, results

    _run_phase2_command(ctx, "monday-pulse", dry_run, _consumer)


@cli.command("update-all-hands-deck")
@click.option("--dry-run", is_flag=True, help="Render but don't update slides.")
@click.option("--check-cadence/--no-check-cadence", default=True,
              help="Skip if not a goals week (default: check).")
@click.pass_context
def update_all_hands_deck_cmd(ctx, dry_run, check_cadence):
    """Update all-hands slide deck with latest KPI metrics (Monday, bi-weekly)."""
    from lib.all_hands_deck import apply_deck_updates, render_deck_updates
    from lib.cron_dispatch import CronConfigError, get_cron_mode

    if check_cadence:
        try:
            mode = get_cron_mode(date.today(), ctx.obj["config"])
            if mode != "goals":
                click.echo(f"update-all-hands-deck: skipped (projects week, mode={mode})")
                return
        except CronConfigError as e:
            click.echo(f"WARNING: cadence check failed ({e}), running anyway.", err=True)

    def _consumer(all_payloads, snapshot_ts, config, dry_run):
        replacements, results = render_deck_updates(all_payloads, snapshot_ts)

        if dry_run:
            for r in replacements:
                click.echo(f"  {r.placeholder} → {r.replacement}")
            apply_results = apply_deck_updates(replacements, dry_run=True)
            return replacements, results + apply_results

        apply_results = apply_deck_updates(replacements, dry_run=False)
        return replacements, results + apply_results

    _run_phase2_command(ctx, "update-all-hands-deck", dry_run, _consumer)


if __name__ == "__main__":
    cli()
