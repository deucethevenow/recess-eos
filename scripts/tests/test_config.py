"""Tests for recess_os.yml config loader."""
import pytest

from lib.config import load_config, get_active_goals, get_meeting, ConfigError


class TestLoadConfig:
    def test_loads_valid_yaml(self, sample_config_yaml):
        config = load_config(sample_config_yaml)
        assert "goals" in config
        assert "meetings" in config
        assert "slack_channels" in config

    def test_missing_file_raises(self, tmp_path):
        nonexistent = tmp_path / "missing.yml"
        with pytest.raises(ConfigError, match="not found"):
            load_config(nonexistent)

    def test_invalid_yaml_raises(self, tmp_path):
        bad = tmp_path / "bad.yml"
        bad.write_text(":\n  - invalid: yaml: structure")
        with pytest.raises(ConfigError, match="parse"):
            load_config(bad)


class TestGetActiveGoals:
    def test_returns_only_active_goals(self, sample_config_yaml):
        config = load_config(sample_config_yaml)
        active = get_active_goals(config)
        assert len(active) == 1
        assert active[0]["asana_goal_id"] == "1213964743621574"

    def test_filters_out_needs_kpi_build(self, tmp_path):
        config_path = tmp_path / "test.yml"
        config_path.write_text("""
goals:
  - asana_goal_id: "1"
    status: "active"
  - asana_goal_id: "2"
    status: "needs_kpi_build"
  - asana_goal_id: "3"
    status: "needs_verification"
""")
        config = load_config(config_path)
        active = get_active_goals(config)
        assert [g["asana_goal_id"] for g in active] == ["1"]


class TestGetMeeting:
    def test_returns_meeting_by_id(self, sample_config_yaml):
        config = load_config(sample_config_yaml)
        meeting = get_meeting(config, "leadership")
        assert meeting["name"] == "Test Leadership L10"

    def test_returns_none_for_unknown(self, sample_config_yaml):
        config = load_config(sample_config_yaml)
        assert get_meeting(config, "nonexistent") is None
