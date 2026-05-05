"""Pre-flight runtime checks for /monday-kpi-update.

Per v3.8 Patch 5 (closes B10 silent rocks=unavailable regression, B11 deck table
row-count drift, B2 partial today-pinning audit):

Pre-flight runs BEFORE the sensitivity gate and BEFORE any surface write. If any
check fails, the entire run aborts and a failure alert is posted to
#kpi-dashboard-notifications.

Required headroom per dept slide table: header row + N metric rows + 2 buffer.
This intentionally exceeds the strict minimum so a future metric addition that
runs before manual deck prep doesn't silently truncate.

Fail-loud rule (C4 fix from review): if any rendered dept has a slide_idx but no
fetch_table_row_count is wired, that's a CONFIG bug — silently skipping the
table-row check would defeat Patch 5. We refuse to run.
"""
from typing import Any, Callable, Dict, List, Optional

from .failure_alert import emit_failure_alert


class PreflightError(Exception):
    """Raised when pre-flight conditions are not met. Halts the entire run."""


def run_preflight(
    *,
    today,
    company_metrics: Dict[str, Any],
    rock_data: Dict[str, Any],
    rendered_per_dept: Dict[str, Dict[str, Any]],
    deck_id: str,
    fetch_table_row_count: Optional[Callable[[str, int], Optional[int]]] = None,
    skip_deck: bool = False,
) -> None:
    failures: List[str] = []
    has_resolved_slides = any(
        p.get("slide_idx") is not None for p in rendered_per_dept.values()
    )

    # 1. Rocks data freshness — closes Probe 9-7 silent regression.
    if not rock_data.get("available", False):
        failures.append(
            f"Rock data unavailable (available={rock_data.get('available')}). "
            "Asana → BQ ETL likely broken. Aborting before any write."
        )

    # 2a. Slide-idx resolution — runs unconditionally UNLESS skip_deck=True.
    #     A dept with rendered rows but no slide_idx is a manual-prep gap
    #     ONLY IF the dept is expected to have a slide (i.e., is in
    #     DEPT_TITLE_MAP). Some depts (bizdev, operations as of 2026-05-05)
    #     are intentionally rendered for Slack/leadership-doc but NOT for
    #     the deck — they're absent from DEPT_TITLE_MAP and the resolver
    #     correctly omits them. Pre-flight should not fail-loud for those.
    #
    #     Session 3 NIT-3: skip_deck=True bypasses these checks entirely
    #     for callers running without a Slides API binding (DECK_ENABLED=0,
    #     --skip-deck flag).
    #
    #     Session 3.6: introduce DEPT_TITLE_MAP dependency to distinguish
    #     "missing slide is a manual-prep error" (dept IS in map but slide
    #     not found) from "dept has no slide by design" (dept absent from
    #     map).
    if not skip_deck:
        from .dept_slide_map import DEPT_TITLE_MAP  # noqa: E402

        for dept_id, payload in rendered_per_dept.items():
            if dept_id not in DEPT_TITLE_MAP:
                continue  # dept intentionally has no slide; not a failure
            if payload.get("slide_idx") is None:
                expected_title = DEPT_TITLE_MAP[dept_id]
                failures.append(
                    f"{dept_id}: no slide_idx resolved (expected slide title "
                    f"'{expected_title}'). Manual prep — create or rename a "
                    "slide with that exact title."
                )

    # 2b. Deck table row counts — closes Probe 9-8 / Session 0 PROBE 2.
    #     fetch_table_row_count is injected for testability — the production
    #     binding lives in the deck writer module so this lib stays import-light.
    #     C4 fix: if any dept has a slide_idx, fetch_table_row_count is required.
    #     Silent skip would defeat the entire Patch 5 contract.
    if not skip_deck:
        from .dept_slide_map import DEPT_TITLE_MAP  # noqa: E402

        if fetch_table_row_count is None:
            if has_resolved_slides:
                failures.append(
                    "Pre-flight cannot run deck table-row check: fetch_table_row_count "
                    "is None but at least one dept has a resolved slide_idx. Either "
                    "wire the Slides API row-count fetcher or rerun with skip_deck=True."
                )
        else:
            for dept_id, payload in rendered_per_dept.items():
                if dept_id not in DEPT_TITLE_MAP:
                    continue  # dept intentionally has no deck slide
                slide_idx = payload.get("slide_idx")
                if slide_idx is None:
                    continue  # already reported in 2a
                row_count = len(payload.get("scorecard_rows", []))
                required = 1 + row_count + 2  # header + N + 2 buffer
                actual = fetch_table_row_count(deck_id, slide_idx)
                if actual is None:
                    failures.append(
                        f"{dept_id}: slide {slide_idx} has NO table — manual prep required."
                    )
                elif actual < required:
                    failures.append(
                        f"{dept_id}: slide {slide_idx} has {actual} rows, "
                        f"needs {required} (1 header + {row_count} metrics + 2 buffer). "
                        "Pad table manually or rerun with skip_deck=True."
                    )

    # 3. Either fail loud, or log the audit trail. I3 fix: do NOT print "OK"
    # before raising — operators scanning logs would miss the trace below.
    if failures:
        msg = "Pre-flight failures:\n" + "\n".join(f"  - {f}" for f in failures)
        emit_failure_alert(surface="preflight", detail=msg)
        raise PreflightError(msg)

    # Only on success: emit the audit trail line. Closes Probe 9-9.
    print(f"Pre-flight PASS — pinned today={today.isoformat()} for run.")
