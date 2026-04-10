"""Tests for the recess_os CLI entry point."""
from click.testing import CliRunner

from recess_os import cli


def test_cli_invokes():
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "recess os" in result.output.lower()


def test_cli_has_sync_to_bq_command():
    runner = CliRunner()
    result = runner.invoke(cli, ["sync-to-bq", "--help"])
    assert result.exit_code == 0


def test_cli_has_push_kpi_goals_command():
    runner = CliRunner()
    result = runner.invoke(cli, ["push-kpi-goals", "--help"])
    assert result.exit_code == 0
