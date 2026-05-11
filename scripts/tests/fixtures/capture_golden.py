"""Phase H.1 — Golden Slack blocks fixture capture.

Captures the Block Kit payload that `monday_kpi_update.main()` posts to Slack
TODAY (under the OLD pipeline — render_one_row → RenderedRow → post_pulse). This
fixture is the regression gate for Batch H.3: post-migration output must be
byte-identical EXCEPT for the 3 W.1 engineering metrics flipping from
"🔨 (Phase 2 migration)" to live values (Features=9, PRDs=18, FSDs=9).

The capture is intentionally end-to-end through `main()` (NOT a direct call into
`render_monday_pulse`) to address Phase H plan v2 round-2 Reviewer Issue #2:
the golden must reflect what production actually produces, including the dept
ordering, sensitivity filtering, header, and rocks section composition.

Run:
    set -a && . ~/Projects/daily-brief-agent/.env && set +a
    export GOOGLE_APPLICATION_CREDENTIALS=/Users/deucethevenowworkm1/.config/bigquery-mcp-key.json
    cd /Users/deucethevenowworkm1/Projects/eos-batch-6-cloud-run
    .venv/bin/python scripts/tests/fixtures/capture_golden.py

Side effects: NONE — does not post to Slack, deck, or doc. Reads from live BQ
and Firestore for metric values + Asana for goals; the Firestore IDEMPOTENCY
marker is mocked so the capture works regardless of whether today's pulse was
already posted.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date as _date
from pathlib import Path
from unittest.mock import MagicMock

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

DASHBOARD_REPO = Path(
    os.environ.get(
        "KPI_DASHBOARD_REPO",
        "/Users/deucethevenowworkm1/Projects/company-kpi-dashboard",
    )
)
sys.path.insert(0, str(DASHBOARD_REPO))
sys.path.insert(0, str(DASHBOARD_REPO / "dashboard"))
sys.path.insert(0, str(DASHBOARD_REPO / "scripts"))

import monday_kpi_update  # noqa: E402


def main() -> int:
    captured: list[dict] = []

    def capture_fn(*, channel_id: str, blocks: list[dict]) -> str:
        captured.append({"channel_id": channel_id, "blocks": blocks})
        return "TS_GOLDEN_CAPTURE"

    # Mock Firestore so the idempotency marker doesn't block the capture.
    # Pattern matches test_main_e2e.py:92-95.
    fake_db = MagicMock()
    fake_doc_ref = fake_db.collection.return_value.document.return_value
    fake_doc_ref.get.return_value.exists = False
    fake_doc_ref.get.return_value.to_dict.return_value = {}

    monday_kpi_update.main(
        skip_deck=True,
        skip_rocks_deck=True,
        skip_slack=False,
        include_leadership_doc=False,
        slack_post_fn=capture_fn,
        firestore_client=fake_db,
        input_fn=lambda _: "y",
    )

    if not captured:
        print(
            "[capture_golden] ERROR: no Slack blocks captured. "
            "Did post_pulse skip via slack_already_posted_today, or did the "
            "sensitivity gate abort?",
            file=sys.stderr,
        )
        return 1

    out = Path(__file__).resolve().parent / f"golden_slack_blocks_{_date.today().isoformat()}.json"
    blocks = captured[0]["blocks"]
    out.write_text(json.dumps(blocks, indent=2))
    size = out.stat().st_size
    print(
        f"[capture_golden] Wrote {out.name}: {len(blocks)} blocks, {size} bytes.",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
