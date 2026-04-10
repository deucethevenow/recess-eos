"""Tests for Asana client wrapper."""
import os
from unittest.mock import MagicMock, patch

import pytest

from lib.asana_client import RecessAsanaClient, AsanaAuthError


class TestAsanaAuth:
    def test_raises_if_no_token(self, monkeypatch):
        monkeypatch.delenv("ASANA_ACCESS_TOKEN", raising=False)
        with pytest.raises(AsanaAuthError, match="ASANA_ACCESS_TOKEN"):
            RecessAsanaClient(workspace_gid="123")

    def test_initializes_with_token(self, monkeypatch):
        monkeypatch.setenv("ASANA_ACCESS_TOKEN", "test-token")
        client = RecessAsanaClient(workspace_gid="123")
        assert client.workspace_gid == "123"


class TestListProjectsInPortfolio:
    @patch("lib.asana_client.asana")
    def test_returns_projects(self, mock_asana, monkeypatch):
        monkeypatch.setenv("ASANA_ACCESS_TOKEN", "test-token")
        mock_portfolios_api = MagicMock()
        mock_portfolios_api.get_items_for_portfolio.return_value = [
            {"gid": "1", "name": "Test Project"}
        ]
        mock_asana.PortfoliosApi.return_value = mock_portfolios_api
        mock_asana.ApiClient.return_value = MagicMock()

        client = RecessAsanaClient(workspace_gid="123")
        result = client.list_projects_in_portfolio("portfolio-1")
        assert result == [{"gid": "1", "name": "Test Project"}]
