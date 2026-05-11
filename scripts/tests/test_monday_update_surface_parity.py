"""Cross-surface parity test for the Monday-pulse pipeline (Phase 0.5 + Phase B+).

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
import ast

import pytest
import yaml
from pathlib import Path

CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "recess_os.yml"
MONDAY_KPI_UPDATE_PATH = Path(__file__).parent.parent / "monday_kpi_update.py"


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


# ─────────────────────────────────────────────────────────────────────────────
# Phase B+ Test #7 — INTEGRATION-LEVEL call-site assertion
# ─────────────────────────────────────────────────────────────────────────────
# Closes the loophole that Test 2 (test_founders_preread_uses_metric_payload_pipeline)
# explicitly does NOT close. Test 2 verifies the adapter exists and produces
# MetricPayload-shaped objects but does NOT verify the production call site
# (monday_kpi_update.py) actually routes founders through the adapter.
#
# DISCOVERY (Phase B+ implementation, 2026-05-10): the Phase 0.5 docstring
# premise — that monday_kpi_update.py:316 → render_one_row was the existing
# founders pre-read render path — was incorrect. DEPT_METRIC_ORDER excludes
# "founders"; line 316 has never processed founders. The founders pre-read
# is currently a Phase 3 placeholder in scripts/recess_os_daily.sh:48.
#
# Phase B+ ships forward-looking infrastructure: monday_kpi_update.py grew an
# explicit `if dept_id == "founders":` branch that routes through the new
# adapter. The branch is dead code today (DEPT_METRIC_ORDER excludes founders)
# but locks in the contract for Phase 3: when founders pre-read implementation
# lands, it MUST go through the adapter. Test #7 enforces structurally so a
# parallel render_one_row-based path can't sneak back in.


def _is_founders_dept_id_check(node) -> bool:
    """AST helper: True iff `node` is an `ast.If` whose test is
    `dept_id == "founders"` (single-string-literal compare, ignoring quote style
    since AST normalizes both to a Constant)."""
    return (
        isinstance(node, ast.If)
        and isinstance(node.test, ast.Compare)
        and isinstance(node.test.left, ast.Name)
        and node.test.left.id == "dept_id"
        and len(node.test.ops) == 1
        and isinstance(node.test.ops[0], ast.Eq)
        and len(node.test.comparators) == 1
        and isinstance(node.test.comparators[0], ast.Constant)
        and node.test.comparators[0].value == "founders"
    )


def _render_one_row_calls_with_founders(tree) -> list:
    """Walk the AST and return ast.Call nodes that are render_one_row(...) calls
    with "founders" as a positional or `dept_id=` keyword argument."""
    hits = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "render_one_row"):
            continue
        positional_founders = any(
            isinstance(arg, ast.Constant) and arg.value == "founders"
            for arg in node.args
        )
        kw_founders = any(
            kw.arg == "dept_id" and isinstance(kw.value, ast.Constant) and kw.value.value == "founders"
            for kw in node.keywords
        )
        if positional_founders or kw_founders:
            hits.append(node)
    return hits


def _render_one_row_calls_under_founders_branch(tree) -> list:
    """For every `if dept_id == "founders":` block — including elif chains, which
    AST encodes as a nested If in `orelse` — return any render_one_row calls in
    its body subtree. Catches the regression the regex-based check missed."""
    hits = []
    for node in ast.walk(tree):
        if not _is_founders_dept_id_check(node):
            continue
        for stmt in node.body:
            for sub in ast.walk(stmt):
                if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name) and sub.func.id == "render_one_row":
                    hits.append(sub)
    return hits


def test_phase_b_plus_no_render_one_row_call_for_founders_dept():
    """Phase B+ Test #7 — monday_kpi_update.py must not call render_one_row
    in any branch where dept_id is "founders".

    Structural AST assertion (Phase C+E F11 — replaces the prior regex-based
    check, which silently allowed `elif dept_id == "founders":` branches).
    Catches:
      1. `render_one_row(entry, "founders", ...)` — positional founders arg
      2. `render_one_row(entry, dept_id="founders", ...)` — keyword arg
      3. Any `render_one_row(...)` call inside an `if dept_id == "founders":`
         OR `elif dept_id == "founders":` block — `ast.walk` traverses both
         branch flavors uniformly because elif is encoded as nested If in
         orelse.

    Future-proofing: if Phase 3 founders pre-read is ever wired by anyone
    other than the adapter, this test fails loud. The adapter
    (lib.founders_preread.build_payloads_for_founders_preread) is the only
    blessed founders code path.
    """
    tree = ast.parse(MONDAY_KPI_UPDATE_PATH.read_text())

    direct_hits = _render_one_row_calls_with_founders(tree)
    assert not direct_hits, (
        "Phase B+ Test #7 FAILED: monday_kpi_update.py calls render_one_row "
        f"with 'founders' as an argument ({len(direct_hits)} occurrence(s) at "
        f"line(s) {[n.lineno for n in direct_hits]}). Use "
        "build_payloads_for_founders_preread() instead — see "
        "scripts/lib/founders_preread.py."
    )

    branch_hits = _render_one_row_calls_under_founders_branch(tree)
    assert not branch_hits, (
        "Phase B+ Test #7 FAILED: an `if/elif dept_id == \"founders\":` block "
        "in monday_kpi_update.py contains a render_one_row call (at line(s) "
        f"{[n.lineno for n in branch_hits]}). The founders branch must route "
        "through build_payloads_for_founders_preread instead."
    )


def test_phase_c_plus_e_test_7_ast_check_catches_elif_regression():
    """Phase C+E F11 — the AST-based Test #7 must catch an `elif dept_id ==
    "founders":` block that calls render_one_row. The prior regex-based check
    failed on this pattern (the regex anchor matched only `if`, not `elif`).
    Asserts that the AST helpers used by Test #7 fire on a synthetic source
    snippet containing the regression pattern.
    """
    bad_source = (
        "def f(entry, dept_id, ctx):\n"
        "    if dept_id == 'sales':\n"
        "        return render_one_row(entry, dept_id, ctx)\n"
        "    elif dept_id == 'founders':\n"
        "        return render_one_row(entry, dept_id, ctx)\n"
    )
    tree = ast.parse(bad_source)

    branch_hits = _render_one_row_calls_under_founders_branch(tree)
    assert len(branch_hits) == 1, (
        "F11 regression: AST helper must catch render_one_row inside an "
        f"elif dept_id == 'founders': block (got {len(branch_hits)} hits)."
    )


def test_phase_c_plus_e_pinned_today_compatible_with_real_compute_pacing():
    """Phase C+E T3 (regression) — `_compute_path_b_fields` must produce
    populated Path B fields when given a normal `today` and a pacing-eligible
    target. Catches the aware/naive datetime mismatch (critic round 1
    CRITICAL): dashboard.utils.pacing._days_in_period builds naive
    q_start/q_end/year_start; subtracting an aware today raises TypeError
    that the function's `except (ValueError, TypeError)` absorbs into
    all-None fields. Without this test, the suite stayed GREEN even though
    every production pace_value was silently None.

    Runs the REAL compute_pacing — no monkeypatch. Tests both naive and
    aware callers (defense-in-depth tzinfo stripping should handle both).
    """
    from datetime import datetime, timezone
    from lib import metric_payloads

    for tz_label, today in [
        ("naive", datetime(2026, 5, 5, 12, 0)),
        ("aware-utc", datetime(2026, 5, 5, 12, 0, tzinfo=timezone.utc)),
    ]:
        result = metric_payloads._compute_path_b_fields(
            raw_value=100.0, target=200.0, period="quarter", today=today,
        )
        assert result["pace_value"] is not None, (
            f"{tz_label} today produced None pace_value — likely TypeError "
            "in compute_pacing._days_in_period silently absorbed. Verify "
            "tzinfo stripping is intact in build_all_payloads, "
            "build_metric_payloads, and _compute_path_b_fields."
        )
        assert result["gap_value"] is not None, (
            f"{tz_label} today produced None gap_value (companion check)."
        )
        assert result["status_3state"] is not None, (
            f"{tz_label} today produced None status_3state (companion check)."
        )


def test_phase_c_plus_e_today_threads_compute_pacing_unit(monkeypatch):
    """Phase C+E T3 (unit) — `_compute_path_b_fields` honors a caller-pinned
    `today` and forwards it to compute_pacing. Locks in the inner-most leg
    of the threading chain. Uses NAIVE today to match production
    semantics (pinning sites strip tzinfo).
    """
    from datetime import datetime
    from lib import metric_payloads
    import dashboard.utils.pacing as real_pacing

    captured: list = []

    def fake_compute_pacing(actual, target, period, today=None, prior_year=None):
        captured.append(today)
        return {"delta": 0.0, "pct": 0.0, "label": "On Pace", "expected": float(target), "yoy_suppress": False}

    monkeypatch.setattr(real_pacing, "compute_pacing", fake_compute_pacing)

    pinned = datetime(2026, 5, 5, 12, 0)  # naive — matches production
    metric_payloads._compute_path_b_fields(
        raw_value=100.0, target=200.0, period="quarter", today=pinned,
    )
    assert captured == [pinned], f"compute_pacing did not receive pinned today: {captured}"


def test_phase_c_plus_e_today_threads_orchestrator_to_build_metric_payloads(
    monkeypatch, leadership_meeting, snapshot_row,
):
    """Phase C+E T3 (integration) — `build_all_payloads` pins `today` once and
    threads it into every per-dept `build_metric_payloads` call. Catches a
    regression where the orchestrator drops the kwarg and each dept silently
    falls back to its own `datetime.now(UTC)`.

    Spying at this layer (rather than at compute_pacing) is robust to which
    metrics happen to be pacing-eligible in the leadership meeting fixture —
    the orchestrator MUST call build_metric_payloads at least once per
    meeting, regardless of whether any metric inside reaches compute_pacing.
    """
    from datetime import datetime, timezone
    from lib import orchestrator

    captured: list = []
    real_build = orchestrator.build_metric_payloads

    def spy_build_metric_payloads(*args, today=None, **kwargs):
        captured.append(today)
        return real_build(*args, today=today, **kwargs)

    monkeypatch.setattr(orchestrator, "build_metric_payloads", spy_build_metric_payloads)

    pinned_aware = datetime(2026, 5, 5, 12, 0, tzinfo=timezone.utc)
    expected_naive = pinned_aware.replace(tzinfo=None)
    orchestrator.build_all_payloads(
        config={"meetings": [leadership_meeting]},
        snapshot_row=snapshot_row,
        snapshot_ts="2026-05-09T06:00:00Z",
        today=pinned_aware,
    )

    assert captured, "build_all_payloads never delegated to build_metric_payloads"
    # Orchestrator strips tzinfo before threading (defense against
    # aware/naive TypeError in dashboard.utils.pacing._days_in_period).
    # Asserting the NAIVE form catches both the threading AND the strip.
    assert all(t == expected_naive for t in captured), (
        f"build_all_payloads did not thread tzinfo-stripped `today` to "
        f"every dept: got {captured}, expected {expected_naive}."
    )


def test_phase_b_plus_founders_branch_imports_adapter():
    """Phase B+ Test #7 (companion) — monday_kpi_update.py must import the
    founders adapter symbol. Without the import, the founders branch can't
    route through the adapter.

    Two-part check:
      1. The import line `from lib.founders_preread import build_payloads_for_founders_preread`
         appears at module level (proves the symbol is bound before the loop runs).
      2. The symbol is referenced somewhere in the file (proves it's actually used,
         not just imported for show).
    """
    src = MONDAY_KPI_UPDATE_PATH.read_text()
    assert "from lib.founders_preread import build_payloads_for_founders_preread" in src, (
        "Phase B+ Test #7: monday_kpi_update.py must import "
        "build_payloads_for_founders_preread from lib.founders_preread. "
        "Without this import, the founders branch has no canonical adapter to call."
    )
    # Symbol referenced in code (not just in the import line). The import line
    # itself contains the symbol once — require at least 2 occurrences.
    assert src.count("build_payloads_for_founders_preread") >= 2, (
        "Phase B+ Test #7: build_payloads_for_founders_preread is imported "
        "but never called in monday_kpi_update.py. Wire it into the "
        "founders branch."
    )
