"""Static policy test: bigquery.Client may only be instantiated in lib/bq_client.py.

Hardening D guard. This test greps the scripts/ tree for any non-canonical
instantiation of google.cloud.bigquery.Client. If a new module sneaks in a
direct client, this test fails in CI before the code reaches main.

Exemptions:
- lib/bq_client.py is the canonical module (it IS the client).
- tests/ may reference `bigquery.Client` in mocks (patch('lib.bq_client.bigquery.Client')
  does NOT instantiate — it's a class reference — but we also allow it
  explicitly for clarity).
"""
import re
from pathlib import Path

import pytest


SCRIPTS_ROOT = Path(__file__).parent.parent
LIB_CANONICAL = SCRIPTS_ROOT / "lib" / "bq_client.py"
TESTS_DIR = SCRIPTS_ROOT / "tests"

# Matches `bigquery.Client(` with optional whitespace
CLIENT_INSTANTIATION_PATTERN = re.compile(r"bigquery\.Client\s*\(")


def _iter_python_files(root: Path):
    """Yield all .py files under root, skipping venv/cache/build dirs."""
    skip_parts = {".venv", "venv", "__pycache__", ".pytest_cache", "build", "dist"}
    for path in root.rglob("*.py"):
        if any(part in skip_parts for part in path.parts):
            continue
        yield path


def test_no_unauthorized_bigquery_client_instantiation():
    """Only lib/bq_client.py may instantiate google.cloud.bigquery.Client.

    Any other module that instantiates the client creates a parallel BQ access
    path that bypasses the Truth Model primitives (load_snapshot, merge_events,
    create_or_replace_view). This invariant is load-bearing for the hardening
    refactor — without it, downstream consumers can drift into inconsistent
    write semantics.
    """
    violations: list[tuple[Path, int, str]] = []

    for py_file in _iter_python_files(SCRIPTS_ROOT):
        # The canonical module is allowed.
        if py_file.resolve() == LIB_CANONICAL.resolve():
            continue
        # Test files use `patch("lib.bq_client.bigquery.Client")` to mock.
        # That's a class reference, not instantiation, but it matches the
        # regex. Allow it inside the tests/ tree.
        if TESTS_DIR in py_file.parents:
            continue

        try:
            text = py_file.read_text()
        except (OSError, UnicodeDecodeError):
            continue

        for lineno, line in enumerate(text.splitlines(), start=1):
            # Strip comments before checking to avoid false-positives from
            # docstrings that document the canonical usage pattern.
            code_part = line.split("#", 1)[0]
            if CLIENT_INSTANTIATION_PATTERN.search(code_part):
                violations.append((py_file, lineno, line.strip()))

    if violations:
        msg_lines = [
            "Unauthorized bigquery.Client() instantiation detected.",
            "Only lib/bq_client.py may instantiate google.cloud.bigquery.Client.",
            "Route BQ access through RecessOSBQClient primitives instead.",
            "",
            "Violations:",
        ]
        for path, lineno, code in violations:
            rel = path.relative_to(SCRIPTS_ROOT)
            msg_lines.append(f"  {rel}:{lineno}  {code}")
        pytest.fail("\n".join(msg_lines))
