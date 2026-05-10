# scripts/lib/ — Agents & Authors Guide

Location-specific gotchas for code in `scripts/lib/`. Read before touching `metric_contract.py`, `metric_payloads.py`, `scorecard_renderer.py`, or `leadership_doc_writer.py`.

For project-wide learnings, see `context/LEARNINGS.md`.
For cross-project memory, see `~/.claude/projects/-Users-deucethevenowworkm1/memory/MEMORY.md`.

---

## 1. There is no `metric_registry.py` here — by design

The KPI Dashboard's `metric_registry.py` is the single source of truth (GOD). Eos is a pure CONSUMER. `metric_contract.py:356` does:

```python
registry_path = Path("~/Projects/company-kpi-dashboard/dashboard/data/metric_registry.py").expanduser()
spec = importlib.util.spec_from_file_location("metric_registry", registry_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
registry = module.METRIC_REGISTRY
```

**Implications:**
- Adding a metric → entry goes in the **dashboard repo's** `metric_registry.py`, NOT here. That's a separate commit, separate PR, separate deploy.
- Tests must NOT do `from scripts.lib.metric_registry import METRIC_REGISTRY` — there's no such module. Use `metric_contract._load_registry()` (the GOD loader) or the conftest.py-injected dashboard path.
- Plans/specs that say "add to eos's metric_registry.py" are wrong by construction. Reject in plan review.

**Cloud Run gotcha:** the hardcoded `~/Projects/...` path resolves only on Deuce's Mac. In a Cloud Run container this fails. The right fix is the `KPI_DASHBOARD_REPO` env-var pattern already used in `scripts/tests/conftest.py:11-21`. If you change `metric_contract.py:356`, make it env-var-overridable.

---

## 2. `MetricContract` is a `frozen=True` dataclass — extending fields is a contract change

`metric_contract.py:65-77` defines `MetricContract` with exactly 12 fields. It's frozen — you cannot add fields by mutation, only by editing the class definition. **Editing the class is a contract-shape change**, not a "quick win."

Today's frozen fields:
```
metric_name, registry_key, snapshot_column, target, transform,
format_spec, sensitivity, status, null_behavior, availability_state,
asana_goal_id, notes
```

**Coming in Phase W.2** (per skinny SoT plan): the dataclass widens to add `live_handler` (Optional[str]) and `period` (Optional[str]) so live-query metrics can flow through the contract. Do NOT add registry-side `live_handler` / `period` keys before the dataclass widens — they become unread metadata until the contract layer consumes them.

**Validation lives in `_validate_registry_entry()` at `metric_contract.py:291-333`.** It only checks `bq_key, format, higher_is_better`. New fields you add silently pass validation but flow nowhere unless `resolve_metric_contract()` reads them.

---

## 3. `status: needs_build` short-circuits the contract — use it for placeholder metrics

The `L&E Bookings Pacing` entry in `config/recess_os.yml` (yaml ~217-223) is the canonical template for "metric appears in scorecard but live handler doesn't exist yet":

```yaml
- name: "<Display Name>"
  registry_key: null
  target: null
  sensitivity: "<public | leadership | founders_only>"
  status: "needs_build"
  null_behavior: "show_needs_build"
  notes: "<one-liner: where the future wiring lives>"
```

**What happens at contract resolution** (`metric_contract.py:153-187`):
- `status == "needs_build"` → skips `_lookup_registry_entry()` AND `_validate_registry_entry()`
- Returns a contract with `availability_state="needs_build"`, `snapshot_column=None`
- Renderer (`metric_payloads._needs_build_payload()`) shows "🔨 Needs Build" badge

**Verified safe pattern** (Phase 0, 2026-05-09): added `Net Revenue Q (Actual)` + `Net Revenue Q (Forecast)` on Sales + Leadership scorecards using this template. `test_all_scorecard_metrics_resolve` (the resolver-coverage test in `scripts/tests/test_kpi_config_consistency.py`) still passes with the new entries.

---

## 4. Two render paths read DIFFERENT config fields — don't assume changes flow everywhere

When you change a metric's `status:` in `config/recess_os.yml`, only one of two render paths picks it up:

| Path | File | Config field consumed | Surface |
|------|------|----------------------|---------|
| Canonical payload pipeline | `metric_payloads.build_metric_payloads()` | yaml `status:` | Slack pulse, all-hands deck, leadership doc |
| Asana founders pre-read | `monday_kpi_update.py:316 → render_one_row()` | dashboard `METRIC_REGISTRY[*].scorecard_status` | Asana founders card |

Same metric. Two config sources. Two verdicts. The yaml `status: manual` flip in Phase 0 (Bank Cash + Conservative Runway) tags the canonical pipeline correctly but is **invisible** to Jack's Asana founders pre-read render.

**Skinny SoT plan collapses this.** Phase 0.5's parity test is the first hard assertion that the two surfaces produce identical values for the same metric.

When debugging "why does X show wrong on surface Y?" — first identify which render path Y uses, then check the config field that path reads.

---

## 5. `static_scorecard_targets.py` — `Renewal Bookings` and `Renewal Pipeline` are SEPARATE metrics

`STATIC_SCORECARD_TARGETS` (lines 34, 37) has both keys. Don't merge them — they're different metrics in the dashboard registry:

| Key | Registry line (dashboard) | Meaning |
|-----|--------------------------|---------|
| `"Renewal Bookings"` | metric_registry.py:2682 | Closed-won renewal $ |
| `"Renewal Pipeline"` | metric_registry.py:764 | Weighted open pipeline for renewal deal-types |

Phase 0 (2026-05-09) renamed the eos yaml display label `"Renewal Bookings Pacing"` → `"Renewal Pipeline"` so the display name matched the registry_key. **STATIC_SCORECARD_TARGETS was deliberately untouched** — collapsing the keys would break `test_static_scorecard_targets_has_exactly_18_keys` and would silently desync eos from the dashboard.

If a plan says "remove `Renewal Bookings` from `STATIC_SCORECARD_TARGETS`" without explaining why the SEPARATE metric should also be dropped, push back.

---

## 6. NaN safety — use `nan_safety.py` helpers for any BQ-derived value

Eos consumes BQ via `bq_client.py` and `metric_payloads.py`. Pandas converts SQL NULL → `float('nan')`, which is truthy. Standard guards FAIL:

```
BANNED:                          SAFE:
int(val or 0)                    safe_int(val)
float(val or 0)                  safe_float(val)
val if val else 0                safe_int(val)
```

Helpers live in `nan_safety.py`. Always import from there for BQ-sourced numerics. Validation at the `.to_dataframe().to_dict()` boundary should go through `_sanitize_nan()`.

---

## 7. When in doubt — read `metric_contract.py:1-13`

The module docstring is the architecture. Re-quote it whenever the team is tempted to add metric logic outside the registry/contract layer:

> The KPI Dashboard metric_registry.py is GOD. This module:
> 1. Takes a scorecard metric config from recess_os.yml
> 2. Looks up the registry_key in metric_registry.py
> 3. Pulls snapshot_column, format, transform from the REGISTRY (not config)
> 4. FAILS LOUDLY if the registry_key doesn't exist OR registry entry is malformed
> 5. FAILS LOUDLY if config tries to override registry-owned logic fields
> 6. Returns a MetricContract with registry-sourced definitions
>
> If a metric changes in the registry, it automatically changes here.
> If a registry_key doesn't match, the build STOPS — no silent degradation.

If you're tempted to handle a metric "specially" in `metric_payloads.py` or `scorecard_renderer.py`, you're in the wrong layer. Fix the registry or the contract.
