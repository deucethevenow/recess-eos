"""Tests for the canonical metric payload layer — the SINGLE source of truth."""
from dataclasses import asdict
from datetime import datetime, timezone, timedelta

import pytest

from lib.metric_payloads import (
    MetricPayload,
    build_metric_payloads,
    filter_by_sensitivity,
    STALE_THRESHOLD_HOURS,
)


# Shared mock registry for all tests
MOCK_REGISTRY = {
    "Pipeline Coverage": {
        "bq_key": "pipeline_coverage",
        "format": "multiplier",
        "higher_is_better": True,
    },
    "Demand NRR": {
        "bq_key": "demand_nrr",
        "format": "percent",
        "higher_is_better": True,
    },
    "Days to Fulfill": {
        "bq_key": "time_to_fulfill_days",
        "format": "days",
        "higher_is_better": False,
    },
    "Revenue YTD": {
        "bq_key": "revenue_actual",
        "format": "currency",
        "higher_is_better": True,
    },
}


class TestMetricPayloadFrozen:
    def test_is_frozen(self):
        payload = MetricPayload(
            metric_name="Test", config_key="test", registry_key="Test",
            snapshot_column="test_col", raw_value=1.0, transformed_value=1.0,
            target=2.0, display_value="1.0", metric_unit="number",
            format_spec="number", transform="raw",
            snapshot_timestamp="2026-04-13T08:00:00Z",
            sensitivity="public", availability_state="live", dept_id="sales",
            notes=None,
        )
        with pytest.raises(AttributeError):
            payload.raw_value = 999  # frozen — cannot mutate


class TestBuildMetricPayloads:
    def test_automated_metric_builds_payload(self):
        """An automated metric with live BQ data produces a full payload."""
        meeting = {
            "id": "sales",
            "scorecard_metrics": [{
                "name": "Pipeline Coverage",
                "registry_key": "Pipeline Coverage",
                "target": 2.5,
                "sensitivity": "public",
                "status": "automated",
                "null_behavior": "show_dash",
            }],
        }
        snapshot = {"pipeline_coverage": 2.1}
        # Use current time so stale threshold (25h) doesn't flip this test
        # from "live" to "stale" as real calendar time advances.
        from datetime import datetime, timezone
        ts = datetime.now(timezone.utc).isoformat()

        payloads = build_metric_payloads(meeting, snapshot, ts, registry=MOCK_REGISTRY)
        assert len(payloads) == 1
        p = payloads[0]
        assert p.metric_name == "Pipeline Coverage"
        assert p.raw_value == 2.1
        assert p.display_value == "2.1x"  # multiplier format
        assert p.availability_state == "live"
        assert p.dept_id == "sales"
        assert p.transformed_value is not None  # has target → transform applied

    def test_needs_build_returns_placeholder(self):
        """needs_build metrics return a placeholder, not a BQ lookup."""
        meeting = {
            "id": "supply",
            "scorecard_metrics": [{
                "name": "Net-New Supply",
                "registry_key": None,
                "target": 100,
                "sensitivity": "public",
                "status": "needs_build",
                "null_behavior": "show_needs_build",
            }],
        }
        payloads = build_metric_payloads(meeting, {}, "2026-04-13T08:00:00Z", registry=MOCK_REGISTRY)
        assert len(payloads) == 1
        assert payloads[0].availability_state == "needs_build"
        assert "Needs Build" in payloads[0].display_value

    def test_null_bq_value_shows_dash(self):
        """If BQ column is null, display_value shows dash per null_behavior."""
        meeting = {
            "id": "sales",
            "scorecard_metrics": [{
                "name": "Pipeline Coverage",
                "registry_key": "Pipeline Coverage",
                "target": 2.5,
                "sensitivity": "public",
                "status": "automated",
                "null_behavior": "show_dash",
            }],
        }
        snapshot = {}  # pipeline_coverage not in snapshot
        payloads = build_metric_payloads(meeting, snapshot, "2026-04-13T08:00:00Z", registry=MOCK_REGISTRY)
        assert payloads[0].display_value == "\u2014"  # em dash
        assert payloads[0].availability_state == "null"

    def test_currency_formatting(self):
        """Currency values format as $X.XM / $XK / $X."""
        meeting = {
            "id": "leadership",
            "scorecard_metrics": [{
                "name": "Revenue YTD",
                "registry_key": "Revenue YTD",
                "target": None,
                "sensitivity": "leadership",
                "status": "automated",
                "null_behavior": "show_dash",
            }],
        }
        snapshot = {"revenue_actual": 1_250_000}
        payloads = build_metric_payloads(meeting, snapshot, "2026-04-13T08:00:00Z", registry=MOCK_REGISTRY)
        assert payloads[0].display_value == "$1.2M"

    def test_percent_formatting(self):
        """Percent values < 1 are multiplied by 100."""
        meeting = {
            "id": "sales",
            "scorecard_metrics": [{
                "name": "Demand NRR",
                "registry_key": "Demand NRR",
                "target": 0.50,
                "sensitivity": "public",
                "status": "automated",
                "null_behavior": "show_dash",
            }],
        }
        snapshot = {"demand_nrr": 0.22}
        payloads = build_metric_payloads(meeting, snapshot, "2026-04-13T08:00:00Z", registry=MOCK_REGISTRY)
        assert payloads[0].display_value == "22.0%"

    def test_days_formatting(self):
        """Days values show as 'X days'."""
        meeting = {
            "id": "am",
            "scorecard_metrics": [{
                "name": "Days to Fulfill",
                "registry_key": "Days to Fulfill",
                "target": 30,
                "sensitivity": "public",
                "status": "automated",
                "null_behavior": "show_dash",
            }],
        }
        snapshot = {"time_to_fulfill_days": 45}
        payloads = build_metric_payloads(meeting, snapshot, "2026-04-13T08:00:00Z", registry=MOCK_REGISTRY)
        assert payloads[0].display_value == "45 days"

    def test_multiple_metrics_in_meeting(self):
        """A meeting with multiple metrics returns one payload per metric."""
        meeting = {
            "id": "sales",
            "scorecard_metrics": [
                {
                    "name": "Pipeline Coverage",
                    "registry_key": "Pipeline Coverage",
                    "target": 2.5,
                    "sensitivity": "public",
                    "status": "automated",
                    "null_behavior": "show_dash",
                },
                {
                    "name": "Demand NRR",
                    "registry_key": "Demand NRR",
                    "target": 0.50,
                    "sensitivity": "public",
                    "status": "automated",
                    "null_behavior": "show_dash",
                },
            ],
        }
        snapshot = {"pipeline_coverage": 2.1, "demand_nrr": 0.22}
        payloads = build_metric_payloads(meeting, snapshot, "2026-04-13T08:00:00Z", registry=MOCK_REGISTRY)
        assert len(payloads) == 2
        names = [p.metric_name for p in payloads]
        assert "Pipeline Coverage" in names
        assert "Demand NRR" in names


class TestFilterBySensitivity:
    def _make_payload(self, name, sensitivity):
        return MetricPayload(
            metric_name=name, sensitivity=sensitivity,
            config_key="", registry_key="", snapshot_column="",
            raw_value=1, transformed_value=1, target=None,
            display_value="", metric_unit="", format_spec="",
            transform="raw", snapshot_timestamp="",
            availability_state="live", dept_id="", notes=None,
        )

    def test_public_excludes_founders_and_leadership(self):
        payloads = [
            self._make_payload("A", "public"),
            self._make_payload("B", "leadership"),
            self._make_payload("C", "founders_only"),
        ]
        result = filter_by_sensitivity(payloads, "public")
        assert len(result) == 1
        assert result[0].metric_name == "A"

    def test_leadership_includes_public(self):
        payloads = [
            self._make_payload("A", "public"),
            self._make_payload("B", "leadership"),
            self._make_payload("C", "founders_only"),
        ]
        result = filter_by_sensitivity(payloads, "leadership")
        assert len(result) == 2
        names = [p.metric_name for p in result]
        assert "A" in names and "B" in names

    def test_founders_includes_all(self):
        payloads = [
            self._make_payload("A", "public"),
            self._make_payload("B", "leadership"),
            self._make_payload("C", "founders_only"),
        ]
        result = filter_by_sensitivity(payloads, "founders_only")
        assert len(result) == 3


class TestStaleness:
    def test_stale_threshold_is_25_hours(self):
        assert STALE_THRESHOLD_HOURS == 25

    def test_marks_stale_when_timestamp_old(self):
        """Snapshot timestamp >25h old → availability_state='stale'."""
        old_ts = (datetime.now(timezone.utc) - timedelta(hours=30)).isoformat()
        meeting = {
            "id": "sales",
            "scorecard_metrics": [{
                "name": "Pipeline Coverage",
                "registry_key": "Pipeline Coverage",
                "target": 2.5,
                "sensitivity": "public",
                "status": "automated",
                "null_behavior": "show_dash",
            }],
        }
        snapshot = {"pipeline_coverage": 2.1}
        payloads = build_metric_payloads(meeting, snapshot, old_ts, registry=MOCK_REGISTRY)
        assert payloads[0].availability_state == "stale"

    def test_fresh_timestamp_is_live(self):
        """Snapshot timestamp <25h old → availability_state='live'."""
        fresh_ts = datetime.now(timezone.utc).isoformat()
        meeting = {
            "id": "sales",
            "scorecard_metrics": [{
                "name": "Pipeline Coverage",
                "registry_key": "Pipeline Coverage",
                "target": 2.5,
                "sensitivity": "public",
                "status": "automated",
                "null_behavior": "show_dash",
            }],
        }
        snapshot = {"pipeline_coverage": 2.1}
        payloads = build_metric_payloads(meeting, snapshot, fresh_ts, registry=MOCK_REGISTRY)
        assert payloads[0].availability_state == "live"

    def test_unparseable_timestamp_is_stale(self):
        """Garbage timestamp string → availability_state='stale' (fail-safe)."""
        meeting = {
            "id": "sales",
            "scorecard_metrics": [{
                "name": "Pipeline Coverage",
                "registry_key": "Pipeline Coverage",
                "target": 2.5,
                "sensitivity": "public",
                "status": "automated",
                "null_behavior": "show_dash",
            }],
        }
        snapshot = {"pipeline_coverage": 2.1}
        payloads = build_metric_payloads(meeting, snapshot, "not-a-real-timestamp", registry=MOCK_REGISTRY)
        assert payloads[0].availability_state == "stale"


class TestContractErrorPath:
    def test_bad_registry_key_produces_error_payload(self):
        """If ContractResolutionError is raised, build_metric_payloads produces an error payload."""
        meeting = {
            "id": "sales",
            "scorecard_metrics": [{
                "name": "Fake Metric",
                "registry_key": "Does Not Exist In Registry",
                "target": 2.5,
                "sensitivity": "public",
                "status": "automated",
                "null_behavior": "show_dash",
            }],
        }
        payloads = build_metric_payloads(meeting, {}, "2026-04-13T08:00:00Z", registry=MOCK_REGISTRY)
        assert len(payloads) == 1
        assert payloads[0].availability_state == "error"
        assert "does NOT exist" in payloads[0].notes


# =============================================================================
# Phase W.1 — Live-handler dispatch (Engineering 3-pack)
# =============================================================================
#
# These tests cover the live-query path: yaml status="live" routes through
# _LIVE_HANDLERS[registry_key] instead of snapshot_row. Phase W.1 wires three
# Engineering metrics (Features Fully Scoped, PRDs Generated, FSDs Generated)
# that have no snapshot column yet — handlers query BQ directly via SQL files
# bundled in dashboard/data/engineering_queries/.

W1_REGISTRY = {
    "Features Fully Scoped": {
        "bq_key": None,            # no snapshot column — live-query path
        "format": "number",
        "higher_is_better": True,
    },
    "PRDs Generated": {
        "bq_key": None,
        "format": "number",
        "higher_is_better": True,
    },
    "FSDs Generated": {
        "bq_key": None,
        "format": "number",
        "higher_is_better": True,
    },
}


class TestLiveStatusContract:
    """The contract layer must accept yaml status="live" and bridge it to
    availability_state="live" without requiring a snapshot_column."""

    def test_live_status_resolves_to_live_availability(self):
        from lib.metric_contract import resolve_metric_contract
        contract = resolve_metric_contract({
            "name": "Features Fully Scoped",
            "registry_key": "Features Fully Scoped",
            "sensitivity": "leadership",
            "status": "live",
            "null_behavior": "show_dash",
        }, registry=W1_REGISTRY)
        assert contract.status == "live"
        assert contract.availability_state == "live"
        assert contract.format_spec == "number"
        # bq_key=None in registry → snapshot_column may be None for live status
        assert contract.snapshot_column is None

    def test_live_status_does_not_require_snapshot_column(self):
        """Status="automated" requires non-null snapshot_column; "live" must not.

        This is the contract-layer tweak that makes W.1's live-query path possible:
        live metrics have no snapshot column today (TODO: snapshot migration in
        teammate handoff ticket), so resolution must succeed with bq_key=None.
        """
        from lib.metric_contract import resolve_metric_contract, ContractResolutionError
        # automated raises when snapshot_column is None
        with pytest.raises(ContractResolutionError):
            resolve_metric_contract({
                "name": "Features Fully Scoped",
                "registry_key": "Features Fully Scoped",
                "sensitivity": "leadership",
                "status": "automated",
                "null_behavior": "show_dash",
            }, registry=W1_REGISTRY)
        # live succeeds with the same registry entry
        contract = resolve_metric_contract({
            "name": "Features Fully Scoped",
            "registry_key": "Features Fully Scoped",
            "sensitivity": "leadership",
            "status": "live",
            "null_behavior": "show_dash",
        }, registry=W1_REGISTRY)
        assert contract.availability_state == "live"


class TestLiveHandlersDict:
    """_LIVE_HANDLERS is the registry-key → callable map. Phase W.1 ships three
    handlers; W.2/W.3/W.4 append more without changing this contract."""

    def test_live_handlers_contains_engineering_3pack(self):
        from lib.metric_payloads import _LIVE_HANDLERS
        assert "Features Fully Scoped" in _LIVE_HANDLERS
        assert "PRDs Generated" in _LIVE_HANDLERS
        assert "FSDs Generated" in _LIVE_HANDLERS

    def test_live_handlers_values_are_callable(self):
        from lib.metric_payloads import _LIVE_HANDLERS
        for key, handler in _LIVE_HANDLERS.items():
            assert callable(handler), f"_LIVE_HANDLERS[{key!r}] is not callable"


class TestLiveHandlerDispatch:
    """build_metric_payloads(status="live") dispatches via _LIVE_HANDLERS and
    populates raw_value from the handler's return — NOT from snapshot_row."""

    def _meeting(self):
        return {
            "id": "engineering",
            "scorecard_metrics": [{
                "name": "Features Fully Scoped",
                "registry_key": "Features Fully Scoped",
                "target": None,
                "sensitivity": "leadership",
                "status": "live",
                "null_behavior": "show_dash",
            }],
        }

    def test_live_dispatch_uses_handler_return_value(self, monkeypatch):
        """When handler returns int, payload.raw_value is that int and state="live"."""
        from lib import metric_payloads
        # Replace handler with deterministic stub
        monkeypatch.setitem(metric_payloads._LIVE_HANDLERS, "Features Fully Scoped", lambda: 9)
        payloads = build_metric_payloads(
            self._meeting(), {}, "2026-05-10T06:00:00Z", registry=W1_REGISTRY,
        )
        assert len(payloads) == 1
        assert payloads[0].raw_value == 9.0  # _safe_optional_float coerces
        assert payloads[0].availability_state == "live"
        assert payloads[0].metric_name == "Features Fully Scoped"
        # Engineering 3-pack has no target → display dash for target_display
        assert payloads[0].target is None
        assert payloads[0].target_display is None

    def test_live_dispatch_handler_returns_none_means_error(self, monkeypatch):
        """When handler returns None (BQ failure / import miss), payload state="error"."""
        from lib import metric_payloads
        monkeypatch.setitem(metric_payloads._LIVE_HANDLERS, "Features Fully Scoped", lambda: None)
        payloads = build_metric_payloads(
            self._meeting(), {}, "2026-05-10T06:00:00Z", registry=W1_REGISTRY,
        )
        assert len(payloads) == 1
        assert payloads[0].raw_value is None
        assert payloads[0].availability_state == "error"

    def test_live_dispatch_handler_missing_means_error(self, monkeypatch):
        """If yaml status="live" but registry_key absent from _LIVE_HANDLERS, error.

        Defense-in-depth — silently dropping the metric or producing a "needs_build"
        badge would mask a real wiring bug. Fail loud at payload construction.
        """
        from lib import metric_payloads
        # Drop the handler entirely
        monkeypatch.setattr(metric_payloads, "_LIVE_HANDLERS", {})
        payloads = build_metric_payloads(
            self._meeting(), {}, "2026-05-10T06:00:00Z", registry=W1_REGISTRY,
        )
        assert len(payloads) == 1
        assert payloads[0].availability_state == "error"
        assert payloads[0].raw_value is None

    def test_live_dispatch_ignores_snapshot_row(self, monkeypatch):
        """raw_value comes from handler — the snapshot_row passed in is irrelevant."""
        from lib import metric_payloads
        monkeypatch.setitem(metric_payloads._LIVE_HANDLERS, "Features Fully Scoped", lambda: 42)
        # Snapshot has noise that would mislead a wrong dispatch path
        payloads = build_metric_payloads(
            self._meeting(),
            {"features_fully_scoped": 999, "Features Fully Scoped": 999},
            "2026-05-10T06:00:00Z",
            registry=W1_REGISTRY,
        )
        assert payloads[0].raw_value == 42.0


class TestEngineering3PackHandlers:
    """The three concrete handler functions. Each must return Optional[int] —
    NEVER 0 on BQ failure (that silently masks errors as "0 features scoped").

    Real-BQ smoke verification lives in
    context/evidence/2026-05-10-phase-w1/02-live-values.txt — not in unit
    tests, to keep the suite hermetic and fast.
    """

    def test_handler_returns_none_when_bq_query_returns_none(self, monkeypatch):
        """Plan-as-drafted bug PA5: `(_run_single_row(...) or {}).get("scoped", 0)`
        silently returns 0 when query fails. Correct: propagate None upstream so
        availability_state="error" can fire instead of fabricating "0 features".
        """
        from lib import metric_payloads
        # Stub _run_engineering_query to simulate BQ failure
        monkeypatch.setattr(
            metric_payloads, "_run_engineering_query",
            lambda *a, **kw: None,
        )
        assert metric_payloads._get_features_fully_scoped() is None
        assert metric_payloads._get_prds_generated() is None
        assert metric_payloads._get_fsds_generated() is None

    def test_handler_returns_int_when_bq_query_returns_value(self, monkeypatch):
        """When the BQ query returns a real value, handler returns it as int."""
        from lib import metric_payloads
        monkeypatch.setattr(
            metric_payloads, "_run_engineering_query",
            lambda sql_filename, primary_subkey: 17,
        )
        assert metric_payloads._get_features_fully_scoped() == 17
        assert metric_payloads._get_prds_generated() == 17
        assert metric_payloads._get_fsds_generated() == 17


class TestEngineeringQueryRunner:
    """_run_engineering_query is the local SQL runner — replaces the call into
    dashboard.data.engineering_client (which imports streamlit at module top
    and crashes in cron). Reads SQL from a path resolver, runs via
    RecessOSBQClient.query, extracts the named primary_subkey."""

    def test_returns_none_on_bq_exception(self, monkeypatch):
        """Network errors, IAM blips, etc. → None (so handler propagates None)."""
        from lib import metric_payloads
        class _Boom:
            def query(self, sql):
                raise RuntimeError("simulated BQ outage")
        monkeypatch.setattr(metric_payloads, "_get_bq_query_client", lambda: _Boom())
        result = metric_payloads._run_engineering_query(
            "card1-features-fully-scoped.sql", "scoped",
        )
        assert result is None

    def test_returns_none_on_empty_result(self, monkeypatch):
        """Zero rows → None."""
        from lib import metric_payloads
        class _Empty:
            def query(self, sql):
                return []
        monkeypatch.setattr(metric_payloads, "_get_bq_query_client", lambda: _Empty())
        result = metric_payloads._run_engineering_query(
            "card1-features-fully-scoped.sql", "scoped",
        )
        assert result is None

    def test_returns_subkey_value_on_success(self, monkeypatch):
        """Happy path — first row, named subkey."""
        from lib import metric_payloads
        class _OK:
            def query(self, sql):
                return [{"scoped": 13, "total_pipeline": 20, "pct": 65}]
        monkeypatch.setattr(metric_payloads, "_get_bq_query_client", lambda: _OK())
        result = metric_payloads._run_engineering_query(
            "card1-features-fully-scoped.sql", "scoped",
        )
        assert result == 13

    def test_returns_none_on_missing_subkey(self, monkeypatch):
        """Subkey absent (schema drift) → None, not 0. Protects against silent
        masking of column renames at the BQ layer."""
        from lib import metric_payloads
        class _Drift:
            def query(self, sql):
                return [{"some_other_col": 42}]
        monkeypatch.setattr(metric_payloads, "_get_bq_query_client", lambda: _Drift())
        result = metric_payloads._run_engineering_query(
            "card1-features-fully-scoped.sql", "scoped",
        )
        assert result is None

    def test_returns_none_when_subkey_value_is_none(self, monkeypatch):
        """BQ NULL → Python None at the sub-key. Must propagate None, NOT
        silently coerce to 0 via safe_int's default. Dormant for COUNTIF/COUNT
        used today; arms when W.2+ wire SUM/AVG/SAFE_DIVIDE which CAN return NULL.
        """
        from lib import metric_payloads
        class _BQNull:
            def query(self, sql):
                return [{"scoped": None, "total_pipeline": 17, "pct": 0}]
        monkeypatch.setattr(metric_payloads, "_get_bq_query_client", lambda: _BQNull())
        result = metric_payloads._run_engineering_query(
            "card1-features-fully-scoped.sql", "scoped",
        )
        assert result is None, f"safe_int(None) leaked through; got {result!r}"


class TestLiveStatusValidation:
    """The contract layer must reject yaml configs that set status="live"
    without a registry_key — the dispatcher is keyed by registry_key so a
    missing one would make the metric structurally unresolvable."""

    def test_live_status_without_registry_key_raises(self):
        from lib.metric_contract import resolve_metric_contract, ContractResolutionError
        with pytest.raises(ContractResolutionError, match="status='live' but no registry_key"):
            resolve_metric_contract({
                "name": "Orphan Metric",
                # registry_key intentionally omitted
                "sensitivity": "public",
                "status": "live",
                "null_behavior": "show_dash",
            }, registry=W1_REGISTRY)
