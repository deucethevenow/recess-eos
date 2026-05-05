"""Patch 2 contract test — founders_only rows never reach public surfaces.

This is the load-bearing safety net documented in
feedback_decision_sensitivity_gate.md after the Apr 29 2026 leak (9 sensitive
decisions hit Asana board, including Ian personnel eval).
"""
from io import StringIO

import pytest

from lib.rendered_row import RenderedRow
from monday_kpi_update import (
    build_dept_section_for_slack,
    confirm_sensitivity_gate,
)


def _row(name, sensitivity, display_label=None):
    return RenderedRow(
        metric_name=name,
        display_label=display_label or name,
        dept_id="leadership",
        sensitivity=sensitivity,
        actual_raw=None,
        target_raw=None,
        status_icon="⚪",
        display="$1",
        is_phase2_placeholder=False,
        is_special_override=False,
    )


def test_founders_only_row_filtered_from_public_slack_section():
    rows = [
        _row("Public Metric", "public"),
        _row("Sensitive Personnel Eval", "founders_only"),
    ]
    blocks = build_dept_section_for_slack(
        "leadership", rows, {}, max_sensitivity="public"
    )
    text = blocks[0]["text"]["text"]
    assert "Public Metric" in text
    assert "Sensitive Personnel Eval" not in text


def test_leadership_row_filtered_from_public_section():
    rows = [
        _row("Public Metric", "public"),
        _row("Leadership Only", "leadership"),
    ]
    blocks = build_dept_section_for_slack(
        "leadership", rows, {}, max_sensitivity="public"
    )
    text = blocks[0]["text"]["text"]
    assert "Public Metric" in text
    assert "Leadership Only" not in text


def test_leadership_row_visible_at_leadership_max_sensitivity():
    rows = [_row("Leadership Only", "leadership")]
    blocks = build_dept_section_for_slack(
        "leadership", rows, {}, max_sensitivity="leadership"
    )
    text = blocks[0]["text"]["text"]
    assert "Leadership Only" in text


def test_founders_only_row_filtered_even_at_leadership_max_sensitivity():
    rows = [_row("Founders Only", "founders_only")]
    blocks = build_dept_section_for_slack(
        "leadership", rows, {}, max_sensitivity="leadership"
    )
    text = blocks[0]["text"]["text"]
    assert "Founders Only" not in text


# ----- The mandatory confirmation gate ------------------------------------- #


def test_sensitivity_gate_aborts_on_anything_other_than_y():
    rendered = {
        "leadership": {
            "scorecard_rows": [_row("X", "public")],
        }
    }
    captured = []
    with pytest.raises(SystemExit):
        confirm_sensitivity_gate(
            rendered,
            input_fn=lambda _prompt: "n",
            print_fn=lambda *a, **kw: captured.append(" ".join(map(str, a))),
        )


def test_sensitivity_gate_proceeds_on_explicit_y():
    rendered = {
        "leadership": {
            "scorecard_rows": [_row("X", "public")],
        }
    }
    confirm_sensitivity_gate(
        rendered,
        input_fn=lambda _prompt: "y",
        print_fn=lambda *a, **kw: None,
    )


def test_sensitivity_gate_classifies_each_row_visibly():
    """Gate output must enumerate founders_only rows explicitly so the operator
    cannot miss them — per the Apr 29 leak, the failure mode was operator
    proceeding without seeing what was being written."""
    rendered = {
        "leadership": {
            "scorecard_rows": [
                _row("Public", "public"),
                _row("Sensitive", "founders_only"),
            ]
        }
    }
    captured: list = []
    confirm_sensitivity_gate(
        rendered,
        input_fn=lambda _prompt: "y",
        print_fn=lambda *a, **kw: captured.append(" ".join(map(str, a))),
    )
    output = "\n".join(captured)
    assert "founders_only (1 rows)" in output
    assert "leadership: Sensitive" in output
