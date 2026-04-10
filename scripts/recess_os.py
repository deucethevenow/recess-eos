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
@click.pass_context
def sync_to_bq(ctx):
    """Sync Asana data into BigQuery (App_Recess_OS dataset)."""
    click.echo("sync-to-bq: not yet implemented (Task 11)")


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
