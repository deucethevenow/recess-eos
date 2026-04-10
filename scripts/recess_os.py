"""Recess OS — One module, every system action.

Usage:
    recess_os sync-to-bq           # Asana → BQ daily sync (8am ET)
    recess_os push-kpi-goals       # BQ → Asana Goals (Friday)
    recess_os post-status          # Goal/Project status narratives
    recess_os monday-pulse         # Slack post to #recess-goals-kpis

Each subcommand reads config/recess_os.yml and
sources credentials from ~/Projects/daily-brief-agent/.env.
"""
from __future__ import annotations

from pathlib import Path

import click

from lib.config import load_config


DEFAULT_CONFIG = Path(__file__).parent.parent / "config" / "recess_os.yml"


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
@click.pass_context
def push_kpi_goals(ctx):
    """Push BQ KPI values into Asana Goal metrics (Sunday cron)."""
    click.echo("push-kpi-goals: not yet implemented (Phase 4)")


@cli.command("post-status")
@click.pass_context
def post_status(ctx):
    """Post Goal/Project status update narratives to Asana."""
    click.echo("post-status: not yet implemented (Phase 4)")


@cli.command("monday-pulse")
@click.pass_context
def monday_pulse(ctx):
    """Post Monday morning EOS pulse to #recess-goals-kpis Slack channel."""
    click.echo("monday-pulse: not yet implemented (Phase 4)")


if __name__ == "__main__":
    cli()
