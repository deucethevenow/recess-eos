"""Cross-surface parity test for the Monday-pulse pipeline (Phase 0.5).

Per LEARNING from 2026-04-18 SSOT incident: writing this test FIRST forces
Phase B+ to ship without surface drift. Both tests fail today (xfail-marked)
because the four render paths use four different rendering pipelines. They
transition to GREEN at the end of Phase B+ when all four surfaces consume
MetricPayload from a single canonical pipeline.

WHY two tests, not one (per Phase 0 cross-reviewer note, 2026-05-09):
  Test 1 catches surface drift across three meeting-leadership-fed paths
  (Slack/Deck/Leadership-doc). Test 2 catches the dual-pipeline loophole —
  the registry-fed founders pre-read render path (monday_kpi_update.py:316
  → render_one_row) consumes registry["scorecard_status"], which is a
  DIFFERENT field from yaml status. Without Test 2, Phase B+ could "pass"
  Test 1 while leaving render_one_row unchanged, masking the unfixed 4th
  surface. Both must transition GREEN to declare Phase B+ done.

WHY raw_value parity, not display string parity (per kpi-critic v1):
  Slack may render '$1.06M', Deck '$1,062,834', Doc '$1.06M (19%)'. All
  three are valid surface conventions and should be allowed to vary. The
  DATA must come from the same upstream raw_value=1_062_834.0 — comparing
  display strings tolerates drift; comparing raw_value catches it.

WHY independent computation per side (per learnings-researcher #2):
  Hand-craft expected snapshot_row, do NOT call build_metric_payloads()
  on both sides — that hides divergence by routing both surfaces through
  one helper. Each surface adapter must independently consume the snapshot
  and emit a MetricPayload; parity is asserted on the resulting objects.

WHY xfail without strict=True:
  Phase B+ lands incrementally (one adapter at a time). With strict=True,
  XPASS on a partially-shipped Phase B+ would fail the suite. Default
  (strict=False) tolerates partial progress; the mark is removed in
  Phase B+ Test #7 when ALL adapters AND ALL Path B fields exist.

WHY raises=(ImportError, AttributeError):
  Per eos-critic Phase 0.5 review (Check P5-B): without raises=, xfail
  silently absorbs ANY exception in the test body — yaml.YAMLError,
  KeyError from a renamed yaml metric, FileNotFoundError if CONFIG_PATH
  resolves wrong, etc. That would mask real bugs. The test's intentional
  failure modes today are exactly two:
    1. ImportError — Phase B+ adapter symbols don't exist yet
    2. AttributeError — MetricPayload lacks Path B fields (pace_value,
       gap_value, status_3state) until Phase B+ extends the dataclass
  Any other exception type is a real bug that must NOT be xfail-masked.

WHY the snapshot_row fixture uses registry snapshot_column names directly:
  Per eos-critic Phase 0.5 review (Check P5-G): metric_payloads.py:101
  does `snapshot_row.get(contract.snapshot_column)`. The registry's
  snapshot_column for "Revenue YTD" is `revenue_ytd`, not the
  human-readable `net_revenue_ytd`. Mismatched fixture keys would make
  every payload silently get raw_value=None, so post-Phase-B+ XPASS
  would be `None == None == None` — trivially true but hollow. Fixture
  keys MUST match the registry's actual snapshot_column field, verified
  via _dashboard_src/dashboard/data/metric_registry.py.
"""
import pytest
import yaml
from pathlib import Path

CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "recess_os.yml"


def _load_meeting(meeting_id: str) -> dict:
    cfg = yaml.safe_load(CONFIG_PATH.read_text())
    for m in cfg.get("meetings", []):
        if m.get("id") == meeting_id:
            return m
    raise KeyError(meeting_id)


def _payloads_via_slack_path(meeting: dict, snapshot_row: dict) -> dict:
    """Get MetricPayload objects via Slack render path. Phase B+ symbol."""
    from lib.monday_pulse import build_payloads_for_slack
    payloads = build_payloads_for_slack(meeting, snapshot_row, "2026-05-09T06:00:00Z")
    return {p.metric_name: p for p in payloads}


def _payloads_via_deck_path(meeting: dict, snapshot_row: dict) -> dict:
    """Get MetricPayload objects via Deck render path. Phase B+ symbol."""
    from lib.deck_writer import build_payloads_for_deck
    payloads = build_payloads_for_deck(meeting, snapshot_row, "2026-05-09T06:00:00Z")
    return {p.metric_name: p for p in payloads}


def _payloads_via_doc_path(meeting: dict, snapshot_row: dict) -> dict:
    """Get MetricPayload objects via Leadership doc render path. Phase B+ symbol."""
    from lib.leadership_doc_writer import build_payloads_for_doc
    payloads = build_payloads_for_doc(meeting, snapshot_row, "2026-05-09T06:00:00Z")
    return {p.metric_name: p for p in payloads}


def _payloads_via_founders_preread_path(meeting: dict, snapshot_row: dict) -> dict:
    """Get MetricPayload objects via Asana founders pre-read render path.

    Phase B+ symbol. Today, monday_kpi_update.py:316 calls
    render_one_row(entry, dept_id, ...) where `entry` comes from
    get_scorecard_metrics_for_dept (registry-fed). The registry exposes
    scorecard_status, which is a DIFFERENT field from yaml status.

    Phase B+ replaces this call site with build_payloads_for_founders_preread
    so the founders pre-read consumes the same MetricPayload pipeline as
    the other three surfaces.
    """
    from lib.founders_preread import build_payloads_for_founders_preread
    payloads = build_payloads_for_founders_preread(meeting, snapshot_row, "2026-05-09T06:00:00Z")
    return {p.metric_name: p for p in payloads}


@pytest.fixture
def leadership_meeting():
    """Real meeting id from config/recess_os.yml line 79.

    Critic v1 fix: was 'monday_pulse_slack' which doesn't exist; would silently
    KeyError and skip all assertions.
    """
    return _load_meeting("leadership")


@pytest.fixture
def founders_meeting():
    """Real meeting id from config/recess_os.yml line 138 — drives the
    Asana founders pre-read render path."""
    return _load_meeting("founders")


@pytest.fixture
def snapshot_row():
    """Hand-crafted fixture (independent computation per learnings #2).

    Keys MUST match METRIC_REGISTRY entries' `snapshot_column` field for
    metrics that both `leadership` and `founders` meetings reference (they
    share Revenue YTD + Take Rate %, leadership additionally has Demand NRR
    + Pipeline Coverage). Verified via:

        from dashboard.data.metric_registry import METRIC_REGISTRY
        METRIC_REGISTRY['Revenue YTD']['snapshot_column']    # 'revenue_ytd'
        METRIC_REGISTRY['Take Rate %']['snapshot_column']    # 'take_rate'
        METRIC_REGISTRY['Demand NRR']['snapshot_column']     # 'demand_nrr'
        METRIC_REGISTRY['Pipeline Coverage']['snapshot_column']  # 'pipeline_coverage'

    Manual metrics (Bank Cash, Conservative Runway) and needs_build metrics
    (Bookings Goal Attainment) bypass the snapshot lookup entirely — they
    don't need fixture columns.
    """
    return {
        "revenue_ytd": 1_062_834.0,
        "take_rate": 0.493,
        "demand_nrr": 0.84,
        "pipeline_coverage": 1.5,
        "snapshot_timestamp": "2026-05-09T06:00:00Z",
    }


@pytest.mark.xfail(
    raises=(ImportError, AttributeError),
    reason=(
        "Phase B+ Test #7 unifies Slack/Deck/Leadership-doc adapters on "
        "MetricPayload + Path B fields (pace_value, gap_value, status_3state). "
        "Today: ImportError (build_payloads_for_* don't exist) and "
        "AttributeError (Path B fields don't exist on MetricPayload). "
        "Mark is removed when all three adapters land AND MetricPayload "
        "gains the Path B fields. raises= scopes failure to the two intentional "
        "modes — any other exception is a real bug, not the planned RED state."
    ),
)
def test_slack_deck_doc_emit_identical_payloads(leadership_meeting, snapshot_row):
    """For every yaml metric on the leadership meeting, Slack+Deck+Leadership-doc
    paths must emit MetricPayload with the same raw_value, target,
    transformed_value, and Path B fields (pace, gap, status_3state).

    Display strings (display_value, target_display) are allowed to vary per
    surface convention — the test catches DATA divergence, not formatting.
    """
    slack = _payloads_via_slack_path(leadership_meeting, snapshot_row)
    deck = _payloads_via_deck_path(leadership_meeting, snapshot_row)
    doc = _payloads_via_doc_path(leadership_meeting, snapshot_row)

    common = set(slack) & set(deck) & set(doc)
    assert common, "no metrics common to all three surfaces — yaml drift?"

    # Sanity gate: at least one common metric must have a non-None raw_value
    # in at least one surface. If every payload is null, the parity assertion
    # below would trivially compare None == None == None and tolerate divergence.
    # Per eos-critic Phase 0.5 Check P5-G — this is the hollow-fixture guard.
    any_non_null = any(
        slack[m].raw_value is not None
        or deck[m].raw_value is not None
        or doc[m].raw_value is not None
        for m in common
    )
    assert any_non_null, (
        "every payload across all three surfaces has raw_value=None — fixture "
        "snapshot_column keys likely don't match registry; parity assertion "
        "would be trivially true"
    )

    for metric in common:
        sl, dk, ld = slack[metric], deck[metric], doc[metric]
        # Upstream numeric truth must match across surfaces:
        assert sl.raw_value == dk.raw_value == ld.raw_value, (
            f"{metric}: raw_value drift — Slack={sl.raw_value} "
            f"Deck={dk.raw_value} Doc={ld.raw_value}"
        )
        assert sl.target == dk.target == ld.target, (
            f"{metric}: target drift — Slack={sl.target} "
            f"Deck={dk.target} Doc={ld.target}"
        )
        assert sl.transformed_value == dk.transformed_value == ld.transformed_value, (
            f"{metric}: transformed_value drift"
        )
        # Path B fields must also match (added in Phase B+):
        assert sl.pace_value == dk.pace_value == ld.pace_value, f"{metric}: pace_value drift"
        assert sl.gap_value == dk.gap_value == ld.gap_value, f"{metric}: gap_value drift"
        assert sl.status_3state == dk.status_3state == ld.status_3state, (
            f"{metric}: status_3state drift"
        )


@pytest.mark.xfail(
    raises=(ImportError, AttributeError),
    reason=(
        "Phase B+ adds build_payloads_for_founders_preread so the founders "
        "pre-read can consume MetricPayload alongside Slack/Deck/Doc. Today: "
        "ImportError — the symbol doesn't exist. Once it exists, AttributeError "
        "until MetricPayload gains the Path B fields. Mark is removed in "
        "Phase B+ Test #7 when adapter + Path B fields both land."
    ),
)
def test_founders_preread_uses_metric_payload_pipeline(founders_meeting, snapshot_row):
    """Asserts that build_payloads_for_founders_preread EXISTS and emits
    MetricPayload-shaped objects with Path B fields populated.

    SCOPE OF THIS TEST (per eos-critic Phase 0.5 Check P5-F):
      What this test verifies:
        - The adapter symbol exists (Phase B+ ships lib/founders_preread.py)
        - Returned objects expose .raw_value, .pace_value, .gap_value,
          .status_3state (Path B fields land in MetricPayload)

      What this test does NOT verify (gap acknowledged):
        - That monday_kpi_update.py:316 actually CALLS the new adapter.
          Phase B+ could ship the symbol and still leave render_one_row
          wired in production. Closing that loophole requires an
          integration-level assertion in Phase B+ Test #7 that
          monday_kpi_update.py no longer references render_one_row for
          the founders dept. The unit-level test here is necessary but
          not sufficient.

    Direct attribute access (not hasattr) is used so AttributeError fires
    when Path B fields are missing — xfail catches it and the failure mode
    is structurally tied to the dataclass schema, not to a hasattr check
    that could silently coexist with stale field names.
    """
    payloads = _payloads_via_founders_preread_path(founders_meeting, snapshot_row)
    assert payloads, "founders pre-read returned no payloads"

    # Direct attribute access — AttributeError raised if Path B fields are
    # missing on MetricPayload. xfail(raises=AttributeError) covers it.
    for metric_name, p in payloads.items():
        # Touch each attribute; AttributeError fires immediately if absent.
        # The values themselves are validated for type-shape only — exact
        # numeric parity across surfaces lives in Test 1.
        assert isinstance(p.raw_value, (int, float, type(None))), (
            f"{metric_name}: raw_value is not numeric/None (not MetricPayload?)"
        )
        assert isinstance(p.pace_value, (int, float, type(None))), (
            f"{metric_name}: pace_value wrong type (Path B not properly typed)"
        )
        assert isinstance(p.gap_value, (int, float, type(None))), (
            f"{metric_name}: gap_value wrong type (Path B not properly typed)"
        )
        assert isinstance(p.status_3state, (str, type(None))), (
            f"{metric_name}: status_3state wrong type (Path B not properly typed)"
        )
