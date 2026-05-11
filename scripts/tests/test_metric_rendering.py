"""Phase H.2 tests — H-adapter producer (build_rich_displays).

Verifies the contracts H.3 / H.4a depend on, including the F-1 fix:

  Dispatch plumbing (mocked dashboard renderer):
    - Routes to _render_metric_line when no bypass condition
    - Invokes renderer once per payload (no fan-out)
    - Unknown registry key → KeyError (not silent None)
    - Sensitivity from dashboard registry threads into RenderedRow
    - None raw_value passes through without crashing
    - Module-level signature pins fire on drift (R-H1.4)

  F-1 fix (UN-mocked end-to-end — catches the critic-review C1 case):
    - W.1 live payload + needs_build status → bypasses dashboard short-circuit
    - Bypass output is the live value, not "🔨 Needs Build"

  Defensive (R-H1.1):
    - Every _LIVE_HANDLERS key exists in METRIC_REGISTRY
"""
from datetime import date
from unittest.mock import patch

import pytest

from lib.metric_payloads import MetricPayload, _format_display


def _payload(
    registry_key: str = "Features Fully Scoped",
    raw_value=9.0,
    target=None,
    sensitivity: str = "public",
    dept_id: str = "engineering",
    availability_state: str = "live",
    **kw,
) -> MetricPayload:
    """Test helper: build a MetricPayload with engineering-archetype defaults.

    MetricPayload has 16 required fields; constructing one inline per test
    obscures the test intent. Named `_payload` to match the grep convention
    used by test_monday_pulse.py, test_all_hands_deck.py, test_recess_os_cli.py.

    `display_value` defaults to the same _format_display call production uses
    (metric_payloads._live_payload:649), so tests against the W.1 bypass path
    see the same string production would emit ("9", not "9.0").
    """
    defaults = dict(
        metric_name=registry_key,
        config_key=registry_key,
        registry_key=registry_key,
        snapshot_column="",
        raw_value=raw_value,
        transformed_value=raw_value,
        target=target,
        display_value=_format_display(raw_value, "number", "show_dash"),
        metric_unit="number",
        format_spec="number",
        transform="raw",
        snapshot_timestamp="2026-05-10T12:00:00",
        sensitivity=sensitivity,
        availability_state=availability_state,
        dept_id=dept_id,
        notes=None,
    )
    defaults.update(kw)
    return MetricPayload(**defaults)


def test_dispatch_routes_to_dashboard_renderer_for_non_bypass_payloads():
    """When the W.1 bypass condition is NOT met (e.g., payload availability_state
    is not 'live'), dispatch routes through dashboard's _render_metric_line and
    the rendered string lands bit-identically on RenderedRow.display.

    Uses availability_state='needs_build' to disable the bypass — this is the
    production shape for a W.1 metric whose _LIVE_HANDLERS handler returned None
    (BQ failure). The bypass only fires when eos has a real live value."""
    from lib import metric_rendering

    expected = "• *Features Fully Scoped*: 🔨 Needs Build"

    with patch.object(metric_rendering, "_render_metric_line", return_value=expected):
        result = metric_rendering.build_rich_displays(
            payloads_per_dept={"engineering": [_payload(
                registry_key="Features Fully Scoped",
                raw_value=None,
                availability_state="needs_build",  # disables W.1 bypass
            )]},
            company_metrics={},
            today=date(2026, 5, 10),
        )

    row = result["engineering"]["scorecard_rows"][0]
    assert row.display == expected
    assert row.is_phase2_placeholder is False
    assert row.metric_name == "Features Fully Scoped"


def test_build_rich_displays_calls_dashboard_renderer_once_per_non_bypass_payload():
    """No accidental fan-out: N non-bypass payloads → exactly N dashboard calls.
    Protects against e.g. a future caller adding a per-surface render loop on
    top of build_rich_displays. Uses availability_state='needs_build' to bypass
    the W.1 bypass and force dispatch to dashboard."""
    from lib import metric_rendering

    payloads = [
        _payload(registry_key="Features Fully Scoped", raw_value=None, availability_state="needs_build"),
        _payload(registry_key="PRDs Generated", raw_value=None, availability_state="needs_build"),
        _payload(registry_key="FSDs Generated", raw_value=None, availability_state="needs_build"),
    ]

    with patch.object(metric_rendering, "_render_metric_line", return_value="x") as mock_render:
        metric_rendering.build_rich_displays(
            payloads_per_dept={"engineering": payloads},
            company_metrics={},
            today=date(2026, 5, 10),
        )

    assert mock_render.call_count == 3, (
        f"Expected one dashboard render per payload (3), got {mock_render.call_count}."
    )


def test_build_rich_displays_handles_unknown_metric_key():
    """An unknown registry_key MUST surface as KeyError (R-H1.1 contract).
    Silent fallback would mean a typo in yaml or a missing registry entry
    renders as blank/empty rather than failing CI."""
    from lib import metric_rendering

    payload = _payload(registry_key="ThisMetricDoesNotExistInRegistry")
    with pytest.raises(KeyError, match="ThisMetricDoesNotExistInRegistry"):
        metric_rendering.build_rich_displays(
            payloads_per_dept={"engineering": [payload]},
            company_metrics={},
            today=date(2026, 5, 10),
        )


def test_dashboard_render_metric_line_signature_pinned_green_path():
    """Successful import of metric_rendering implies both signature pins held
    at module-load time. This is the green-path counterpart to the mutation
    xfail below."""
    from lib import metric_rendering

    assert metric_rendering._EXPECTED_RENDER_METRIC_LINE_SIG == (
        "(canonical_name, entry, dept, company_metrics)"
    )
    assert metric_rendering._EXPECTED_RENDER_LIVE_METRIC_SIG == (
        "(entry, dept, company_metrics, canonical_name)"
    )


@pytest.mark.xfail(
    raises=RuntimeError,
    strict=True,
    reason=(
        "Mutating the expected dashboard signature MUST raise RuntimeError. "
        "strict=True ensures the run fails if the assertion silently doesn't fire."
    ),
)
def test_dashboard_signature_pin_fires_on_drift():
    """R-H1.4 mitigation: if dashboard's private _render_metric_line signature
    drifts and our pinned expected string doesn't match, the H-adapter must
    fail LOUD at import. Simulate drift by calling _assert_dashboard_signature
    with a bogus expected string."""
    from lib import metric_rendering
    from post_monday_pulse import _render_metric_line  # type: ignore

    metric_rendering._assert_dashboard_signature(
        _render_metric_line, "(this_is_not_the_real_signature)"
    )


def test_build_rich_displays_sensitivity_filter_preserved(monkeypatch):
    """Dashboard registry-derived sensitivity threads into RenderedRow
    unchanged. Downstream consumer writers (slack/deck/doc) keep doing the
    filtering — H.2 does not introduce a new filter site."""
    from lib import metric_rendering

    monkeypatch.setattr(
        metric_rendering, "get_scorecard_dept_sensitivity", lambda entry, dept: "founders_only"
    )
    monkeypatch.setattr(
        metric_rendering, "_render_metric_line", lambda c, e, d, cm: "bullet"
    )

    result = metric_rendering.build_rich_displays(
        payloads_per_dept={"engineering": [_payload(
            registry_key="Features Fully Scoped",
            availability_state="needs_build",  # disables W.1 bypass; tests dispatch path
        )]},
        company_metrics={},
        today=date(2026, 5, 10),
    )
    row = result["engineering"]["scorecard_rows"][0]
    assert row.sensitivity == "founders_only"


def test_build_rich_displays_handles_none_raw_value():
    """A payload with raw_value=None has availability_state='error' or 'null'
    in production (metric_payloads.py:622). The W.1 bypass condition requires
    availability_state=='live', so a None-value payload dispatches to dashboard
    which already returns a dash for missing values."""
    from lib import metric_rendering

    with patch.object(metric_rendering, "_render_metric_line", return_value="—"):
        result = metric_rendering.build_rich_displays(
            payloads_per_dept={"engineering": [_payload(
                registry_key="Features Fully Scoped",
                raw_value=None,
                availability_state="error",  # matches production for raw_value=None
            )]},
            company_metrics={},
            today=date(2026, 5, 10),
        )

    row = result["engineering"]["scorecard_rows"][0]
    assert row.actual_raw is None
    assert row.display == "—"


def test_metric_registry_keys_cover_all_w1_payloads():
    """R-H1.1 mitigation: every key in _LIVE_HANDLERS must exist in dashboard's
    METRIC_REGISTRY. Without this, build_rich_displays raises KeyError at
    runtime for the W.1 hero metrics. Catches the gap at test time before it
    can fire in cron."""
    from lib.metric_payloads import _LIVE_HANDLERS
    from data.metric_registry import METRIC_REGISTRY  # type: ignore

    missing = [k for k in _LIVE_HANDLERS if k not in METRIC_REGISTRY]
    assert not missing, (
        f"Live handlers reference registry keys not in METRIC_REGISTRY: {missing}. "
        f"build_rich_displays will raise KeyError for these at runtime. "
        f"Either add a matching METRIC_REGISTRY entry in the dashboard repo or "
        f"rename the _LIVE_HANDLERS key to match an existing registry key."
    )


def test_w1_handler_keys_currently_map_to_needs_build_entries():
    """C2 from critic-review: documents the F-1 trap — every _LIVE_HANDLERS key
    currently has scorecard_status='needs_build' in the dashboard registry,
    which is why the W.1 bypass in metric_rendering exists.

    When dashboard flips these entries from needs_build → live (Phase Final or
    later), this test will FAIL — the signal to drop the bypass and let
    dashboard render them directly via _render_live_metric. This is the
    contract that prevents the bypass from silently outliving its purpose.
    """
    from lib.metric_payloads import _LIVE_HANDLERS
    from data.metric_registry import METRIC_REGISTRY  # type: ignore

    non_needs_build = [
        k for k in _LIVE_HANDLERS
        if METRIC_REGISTRY[k].get("scorecard_status") != "needs_build"
    ]
    assert not non_needs_build, (
        f"Dashboard registry status changed for: {non_needs_build}. "
        f"The W.1 bypass in metric_rendering._is_w1_bypass_case may now be "
        f"unnecessary for these keys — audit and consider removing the bypass."
    )


def test_w1_live_payload_bypasses_dashboard_needs_build_short_circuit():
    """F-1 verification (UN-mocked, production path) — closes critic-review C1.

    When eos has a live raw_value for a metric that dashboard registry marks as
    needs_build, build_rich_displays MUST bypass dashboard's _render_metric_line.
    Otherwise dashboard's status-needs_build short-circuit (post_monday_pulse.py
    line 935) returns '🔨 Needs Build' regardless of eos's live value — exactly
    the F-1 leadership-doc bug Phase H exists to fix.

    No mocks: this exercises the actual cross-repo dispatch + bypass. If this
    test regresses, the F-1 leadership-doc bug returns.
    """
    from lib import metric_rendering

    payload = _payload(
        registry_key="Features Fully Scoped",
        raw_value=9.0,
        availability_state="live",
        display_value="9",  # production-shape (matches _format_display output)
    )

    result = metric_rendering.build_rich_displays(
        payloads_per_dept={"engineering": [payload]},
        company_metrics={},
        today=date(2026, 5, 10),
    )

    display = result["engineering"]["scorecard_rows"][0].display
    assert "9" in display, f"Expected '9' in display, got: {display!r}"
    assert "Needs Build" not in display, (
        f"Display contains 'Needs Build', meaning dashboard's needs_build "
        f"short-circuit fired and F-1 regressed. Got: {display!r}"
    )
    assert "Features Fully Scoped" in display, (
        f"Display missing label 'Features Fully Scoped'. Got: {display!r}"
    )


def test_is_w1_bypass_case_fires_for_live_payload_with_needs_build_entry():
    """Pinned dispatch condition: live raw + needs_build registry = bypass."""
    from lib.metric_rendering import _is_w1_bypass_case

    payload = _payload(availability_state="live")
    entry = {"scorecard_status": "needs_build"}
    assert _is_w1_bypass_case(payload, entry) is True


def test_is_w1_bypass_case_skips_when_registry_is_live():
    """Dashboard already renders correctly for live entries — no bypass needed."""
    from lib.metric_rendering import _is_w1_bypass_case

    payload = _payload(availability_state="live")
    entry = {"scorecard_status": "live"}
    assert _is_w1_bypass_case(payload, entry) is False


def test_is_w1_bypass_case_skips_when_payload_is_not_live():
    """Bypass requires a real live value — error/null/needs_build payloads
    dispatch to dashboard, which renders them correctly (dash or placeholder)."""
    from lib.metric_rendering import _is_w1_bypass_case

    entry = {"scorecard_status": "needs_build"}
    for state in ("error", "null", "needs_build", "stale", "manual"):
        payload = _payload(availability_state=state, raw_value=None)
        assert _is_w1_bypass_case(payload, entry) is False, (
            f"Bypass fired for availability_state={state!r}, expected False"
        )
