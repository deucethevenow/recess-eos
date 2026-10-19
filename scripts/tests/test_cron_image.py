"""Contract tests for the recess-cron image and the Monday cron wrapper.

The Monday job refreshes the dept all-hands slides through the dashboard's
scripts/dept_slides.py (called by post_monday_pulse.py --post). These tests fail
if the image stops shipping that file or its Slides client, and pin the
PULSE_SKIP_SLACK mode used for a test run that must not post to Slack.
"""

import stat
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = REPO_ROOT / "Dockerfile.cron"
REQUIREMENTS = REPO_ROOT / "scripts" / "requirements-cloud.txt"
MONDAY_CRON = REPO_ROOT / "scripts" / "monday_cron.sh"


def test_image_copies_dept_slides():
    text = DOCKERFILE.read_text()
    assert "COPY _dashboard_src/scripts/dept_slides.py ./scripts/dept_slides.py" in text


def test_image_build_fails_if_dept_slides_cannot_import():
    assert 'python -c "import dept_slides"' in DOCKERFILE.read_text()


def test_requirements_include_slides_client():
    reqs = [line.split("#")[0].strip() for line in REQUIREMENTS.read_text().splitlines()]
    assert any(req.startswith("google-api-python-client") for req in reqs)


def _run_cron(tmp_path, env_extra):
    """Run monday_cron.sh with stub `python` and `timeout` that log their args."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "calls.log"
    stubs = {
        # timeout --kill-after=15s 360s <cmd...>  ->  exec <cmd...>
        "timeout": '#!/bin/bash\nshift 2\nexec "$@"\n',
        "python": f'#!/bin/bash\necho "$*" >> "{log}"\nexit "${{STUB_EXIT:-0}}"\n',
    }
    for name, body in stubs.items():
        p = bin_dir / name
        p.write_text(body)
        p.chmod(p.stat().st_mode | stat.S_IEXEC)
    env = {"PATH": f"{bin_dir}:/usr/bin:/bin", **env_extra}
    proc = subprocess.run(["bash", str(MONDAY_CRON)], env=env, capture_output=True, text=True)
    calls = log.read_text().splitlines() if log.exists() else []
    return proc, calls


def test_default_run_posts_pulse(tmp_path):
    proc, calls = _run_cron(tmp_path, {})
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert calls == ["/app/scripts/post_monday_pulse.py --post"]


def test_skip_slack_never_posts_and_refreshes_slides(tmp_path):
    proc, calls = _run_cron(tmp_path, {"PULSE_SKIP_SLACK": "1"})
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert not any("--post" in c for c in calls)
    assert calls == [
        "/app/scripts/post_monday_pulse.py",
        "/app/scripts/dept_slides.py --apply",
    ]


def test_skip_slack_ignores_old_deck_step(tmp_path):
    proc, calls = _run_cron(tmp_path, {"PULSE_SKIP_SLACK": "1", "DECK_ENABLED": "1"})
    assert not any("update-all-hands-deck" in c for c in calls)


def test_skip_slack_slide_failure_fails_the_job(tmp_path):
    proc, _ = _run_cron(tmp_path, {"PULSE_SKIP_SLACK": "1", "STUB_EXIT": "1"})
    assert proc.returncode == 1
