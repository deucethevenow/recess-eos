# ABM Portfolio Schema — Canonical Contract

> **Purpose:** This document defines the schema, custom fields, lifecycle phases, and reporting contract that BOTH ABM Rocks adhere to. Rock 1 (Demand ABM, Danny) and rock-005 (Supply ABM, Ian) MUST use these field names and lifecycle states. The shared L10 reporting infrastructure (`v_abm_portfolio_status` BQ view + `/abm-l10-report` skill) reads from this contract — divergence breaks reporting for both rocks.
>
> **Owners:** Deuce (architecture), Danny (demand), Ian (supply)
>
> **Created:** 2026-04-06 — part of Recess OS Rock 5 (Phase 1.5)
>
> **Status:** Active. If you change this doc, ping both Rock owners (Danny + Ian) so they update their template projects to match.

---

## Why a shared schema

Both ABM Rocks produce many individual ABM plans as Asana projects. Without a shared schema:
- Each Rock builds its own L10 reporting → duplicate work, drift over time
- Custom fields drift in name and type → reporting breaks silently
- "Stale" definitions vary → confusing leadership conversations

With a shared schema:
- One BQ view (`v_abm_portfolio_status`) serves both Rocks
- One L10 report skill (`/abm-l10-report`) used by both Sales L10 (Danny) and Supply L10 (Ian)
- Schema changes flow through one place — both rocks stay in sync

---

## Asana portfolios

Two parent portfolios in Asana, one per Rock:

| Portfolio Name | Rock | Owner | Child Project Count (target) |
|---|---|---|---|
| `Q2 2026 Demand ABM` | Rock 1 (NRR via ABM) | Danny Sears | ~30 (10 per AE × 3 AEs) |
| `Q2 2026 Supply ABM` | rock-005 (Supply) | Ian / DRI TBD | TBD |

**Each child project** in either portfolio is one ABM plan = one target account.

---

## ABM Project Lifecycle (5 phases)

Every ABM project — demand or supply — flows through the same 5 phases:

| Phase | Asana Section Name | Definition of Done |
|---|---|---|
| **1. Plan Built** | `Phase 1 — Plan Built` | Strategic plan signed off by Rock owner. Notion plan doc linked. Tier assigned. Total opportunity sized. |
| **2. Marketing Build** | `Phase 2 — Marketing Build` | Assets shipping (sequences drafted, creative produced, landing pages live). Champion identified. |
| **3. Outbound Execution** | `Phase 3 — Outbound Execution` | Sequences live in HubSpot. Multi-thread engagement (3+ contacts at account). At least 1 meaningful customer touch. |
| **4. Conversion** | `Phase 4 — Conversion` | Proposal sent → decision phase. HubSpot deal in late stage. |
| **5. Win/Loss Capture** | `Phase 5 — Win/Loss Capture` | Outcome logged. Lessons captured in Notion. Marked Closed-Won, Closed-Lost, or Stale. |

---

## Custom Fields on Each ABM Project

These custom fields MUST exist on every project in both portfolios. Field names are a documented stable contract — see the "Custom Field Lookup Rule" section below for how consumers should resolve them.

| Field Name | Type | Required | Values / Example | Notes |
|---|---|---|---|---|
| `portfolio_id` | Text | ✅ | `Q2 2026 Demand ABM` or `Q2 2026 Supply ABM` | Used by view to filter |
| `ae_owner` | Text | ✅ (demand) | `Andy Cooper`, `Danny Sears`, `Katie Olmstead` | Demand portfolio only |
| `dri` | Text | ✅ (supply) | Owner name | Supply portfolio only — alias of `ae_owner` for reporting consistency |
| `tier` | Number | ✅ | `1`, `2`, or `3` | Drives stale detection threshold |
| `status` | Enum | ✅ | `Research` / `Plan Built` / `Marketing Build` / `In Execution` / `Closed-Won` / `Closed-Lost` / `Stale` | The phase label that drives reporting |
| `total_opportunity_usd` | Number | ✅ | `250000.00` | Float, USD |
| `linked_notion_plan` | URL | ✅ | Notion URL | Versioned — points to active version |
| `hubspot_company_id` | Text | ⚠️ | HubSpot company GID | Required for HubSpot deal joins |
| `last_refreshed_at` | Date | ✅ | `2026-04-12T08:00:00Z` | Updated when plan reviewed |
| `last_engagement_at` | Date | ✅ | Most recent meaningful customer touch | Drives stale detection |
| `competitor_detected` | Text | ❌ | Optional — name of competitor | Free text |

### Note on `ae_owner` vs `dri`

For reporting uniformity, the BQ view treats `ae_owner` (demand) and `dri` (supply) as the same logical column. The view aliases both to `owner_name` in the output. Rock owners do not need to rename the underlying Asana field.

---

## Custom Field Lookup Rule (Phase 1.5 contract — added 2026-04-09)

The Phase 1 sync writes `custom_fields_json` to `eos_projects` in a **dual-format** JSON:

```json
{
  "fields_by_name": {
    "portfolio_id": "Q2 2026 Demand ABM",
    "ae_owner": "Andy Cooper",
    "tier": 1,
    ...
  },
  "fields_by_gid": {
    "1203876543210": "Q2 2026 Demand ABM",
    "1203876543211": "Andy Cooper",
    "1203876543212": 1,
    ...
  }
}
```

**Both views hold identical data**, keyed differently. This gives us resilience against field renames while preserving human readability.

### Consumer rules (STRICT)

1. **Downstream logic MUST prefer `fields_by_gid`** when looking up custom field values for:
   - View definitions (`v_abm_portfolio_status`)
   - Skills and CLI commands (`/abm-l10-report`, status commands)
   - Automation code (sync scripts, routing logic)

   Example:
   ```sql
   -- PREFERRED (GID-keyed — survives renames):
   JSON_VALUE(custom_fields_json, '$.fields_by_gid."1203876543210"') AS portfolio_id

   -- ALLOWED for human-readable debug output only:
   JSON_VALUE(custom_fields_json, '$.fields_by_name.portfolio_id') AS portfolio_id
   ```

2. **`fields_by_name` is for human-readable output only** — sample output files, debug queries, error messages. If an Asana field is renamed, `fields_by_name` silently breaks but `fields_by_gid` keeps working.

3. **Field names are a stable contract** — listed in the "Custom Fields" table above. Renames MUST follow the "Schema Change Process" at the bottom of this document AND notify both Rock owners (Danny + Ian). But even with the contract, the `fields_by_gid` path is the safety net for when someone forgets the process.

4. **GID mapping for downstream consumers** lives in `~/Projects/eos/config/recess_os.yml` under `asana_custom_field_gids:` once Phase 1.5 starts and the actual GIDs are known. Example:
   ```yaml
   asana_custom_field_gids:
     portfolio_id: "1203876543210"
     ae_owner: "1203876543211"
     tier: "1203876543212"
   ```
   The `v_abm_portfolio_status` view reads these GIDs from a parameterized query or hardcodes them after schema freeze.

5. **If a new field is added to Asana**, update BOTH this document AND the `asana_custom_field_gids` config block. Update the view AFTER both are in sync.

### Why dual-format instead of GID-only

GID-only would be rename-safe but unreadable when debugging. A DBA querying `eos_projects` directly would see `{"1203876543210": "Q2 2026 Demand ABM", ...}` with no idea which field that is. Dual-format costs ~2x the bytes in `custom_fields_json` (a few KB per project max) and gives us both safety and debuggability.

---

## Stale Definition (canonical)

A plan is **Stale** when:
- **Tier 1:** `last_engagement_at` has not changed in **7+ days**
- **Tier 2 or 3:** `last_engagement_at` has not changed in **14+ days**

This threshold lives in the BQ view (`v_abm_portfolio_status`). If the view changes, both rocks see the new threshold immediately — no per-rock config drift.

Stale plans appear with a ⚠️ in `/abm-l10-report` output and link directly to the Asana project URL for one-click follow-up.

---

## BigQuery view: `v_abm_portfolio_status`

Single view that joins Asana project data (synced via the existing `sync_to_bq` Phase 1 work, extended in Phase 1.5 to capture custom fields) with HubSpot deal data and Firestore quota targets.

```sql
-- App_Recess_OS.v_abm_portfolio_status
-- Created in Phase 1.5 of Rock 5 (Recess OS)
-- Consumed by /abm-l10-report skill

CREATE OR REPLACE VIEW `stitchdata-384118.App_Recess_OS.v_abm_portfolio_status` AS

WITH base AS (
  SELECT
    p.asana_project_id,
    p.name AS plan_name,
    JSON_VALUE(p.custom_fields_json, '$.portfolio_id') AS portfolio_id,
    COALESCE(
      JSON_VALUE(p.custom_fields_json, '$.ae_owner'),
      JSON_VALUE(p.custom_fields_json, '$.dri')
    ) AS owner_name,
    SAFE_CAST(JSON_VALUE(p.custom_fields_json, '$.tier') AS INT64) AS tier,
    JSON_VALUE(p.custom_fields_json, '$.status') AS status,
    SAFE_CAST(JSON_VALUE(p.custom_fields_json, '$.total_opportunity_usd') AS FLOAT64) AS total_opportunity_usd,
    JSON_VALUE(p.custom_fields_json, '$.linked_notion_plan') AS linked_notion_plan,
    JSON_VALUE(p.custom_fields_json, '$.hubspot_company_id') AS hubspot_company_id,
    SAFE_CAST(JSON_VALUE(p.custom_fields_json, '$.last_refreshed_at') AS TIMESTAMP) AS last_refreshed_at,
    SAFE_CAST(JSON_VALUE(p.custom_fields_json, '$.last_engagement_at') AS TIMESTAMP) AS last_engagement_at,
    JSON_VALUE(p.custom_fields_json, '$.competitor_detected') AS competitor_detected,
    p.synced_at,
    -- Stale detection by tier
    CASE
      WHEN SAFE_CAST(JSON_VALUE(p.custom_fields_json, '$.tier') AS INT64) = 1
           AND TIMESTAMP_DIFF(CURRENT_TIMESTAMP(),
                              SAFE_CAST(JSON_VALUE(p.custom_fields_json, '$.last_engagement_at') AS TIMESTAMP),
                              DAY) >= 7
        THEN TRUE
      WHEN SAFE_CAST(JSON_VALUE(p.custom_fields_json, '$.tier') AS INT64) IN (2, 3)
           AND TIMESTAMP_DIFF(CURRENT_TIMESTAMP(),
                              SAFE_CAST(JSON_VALUE(p.custom_fields_json, '$.last_engagement_at') AS TIMESTAMP),
                              DAY) >= 14
        THEN TRUE
      ELSE FALSE
    END AS is_stale
  FROM `stitchdata-384118.App_Recess_OS.eos_projects` p
  WHERE JSON_VALUE(p.custom_fields_json, '$.portfolio_id') IN (
    'Q2 2026 Demand ABM',
    'Q2 2026 Supply ABM'
  )
  -- Most recent sync only
  AND p.synced_at = (
    SELECT MAX(synced_at)
    FROM `stitchdata-384118.App_Recess_OS.eos_projects`
    WHERE asana_project_id = p.asana_project_id
  )
)

SELECT
  portfolio_id,
  owner_name,
  tier,
  status,
  COUNT(*) AS plan_count,
  SUM(total_opportunity_usd) AS total_opportunity,
  SUM(CASE WHEN status = 'Closed-Won' THEN total_opportunity_usd ELSE 0 END) AS booked,
  SUM(CASE WHEN status IN ('Marketing Build', 'In Execution') THEN total_opportunity_usd ELSE 0 END) AS in_progress,
  SUM(CASE WHEN is_stale THEN 1 ELSE 0 END) AS stale_count,
  MAX(last_refreshed_at) AS portfolio_last_refresh,
  MIN(last_engagement_at) AS oldest_engagement
FROM base
GROUP BY portfolio_id, owner_name, tier, status;
```

### View characteristics

- **Empty portfolio handling:** Returns 0 rows (not errors) when a portfolio has no projects. Consumers must `IFNULL`/`COALESCE` aggregates.
- **Sync freshness:** Reads only the most recent sync per project (via the `synced_at` partition).
- **Cross-rock reuse:** Same view, both rocks. Filter by `portfolio_id` in the consumer.
- **Performance target:** <30 seconds for full L10 report query.

---

## L10 Report Skill: `/abm-l10-report`

New skill at `~/.claude/commands/abm-l10-report.md`. Reads from `v_abm_portfolio_status`. Used by both Danny's Sales L10 and Ian's Supply L10.

### Invocation

```
/abm-l10-report --portfolio=demand    # → Q2 2026 Demand ABM
/abm-l10-report --portfolio=supply    # → Q2 2026 Supply ABM
/abm-l10-report --portfolio=both      # → both portfolios in one report
```

### Output format (canonical example)

```
ABM Portfolio: Demand — Week of 2026-04-13
─────────────────────────────────────
Total plans: 30
By status:
  Plan Built:       8  (27%)
  Marketing Build:  10 (33%)
  In Execution:     7  (23%)
  Closed-Won:       2  (7%)
  Closed-Lost:      1  (3%)
  Stale (7d+ T1, 14d+ T2/3):  2  ⚠️

Weekly movement:
  + 4 plans advanced phases this week
  - 1 plan went stale this week
  + 1 plan closed-won this week ($85K)

Pacing health:
  Phase II milestone: 2026-04-25 — on track
  Phase III milestone (2026-05-15): $1.95M target vs $642K actual
    In-flight existing-brand $: $451K
    New-ABM-driven $:           $191K

By owner:
  Andy Cooper:     10 plans, 3 in execution, 1 closed-won, $85K booked
  Danny Sears:     10 plans, 2 in execution, 1 closed-won, $0 booked
  Katie Olmstead:  10 plans, 2 in execution, 0 closed-won, $0 booked

Top 5 plans needing attention:
  - Acme Corp (Andy Cooper) — stale 9 days, Tier 1
    https://app.asana.com/0/<project_gid>
  - Globex (Katie Olmstead) — Phase II milestone slipping
    https://app.asana.com/0/<project_gid>
  - Initech (Danny Sears) — competitor detected (Recess Brain)
    https://app.asana.com/0/<project_gid>
  - SoylentCo (Andy Cooper) — champion churn risk
    https://app.asana.com/0/<project_gid>
  - Sirius Cybernetics (Katie Olmstead) — no engagement 12 days, Tier 2
    https://app.asana.com/0/<project_gid>
```

### Pacing source

The "Phase III milestone — target vs actual" section pulls from existing dashboard metrics, not from this view:
- **Target:** Firestore `demand_sales_goals/2026` quarterly Bookings/Net Rev
- **Actual:** `App_KPI_Dashboard.kpi_daily_snapshot.gmv_waterfall_q_*` columns
- **In-flight existing-brand $:** Existing closed-won deals minus deals from ABM portfolio
- **New-ABM-driven $:** Closed-won deals where `linked_notion_plan IS NOT NULL`

This is a JOIN, not a duplicate calculation. Reporting stays consistent with the company KPI dashboard.

---

## Acceptance Criteria

Per the original spec:

- ✅ L10 report runs in <30 seconds against live BQ data
- ✅ Both demand and supply ABM portfolios are covered
- ✅ "Stale" definition is consistent (7d Tier 1, 14d Tier 2/3) and lives in the view
- ✅ Output format renders cleanly in Markdown for L10 prep docs
- ✅ Stale plans link directly to the Asana project URL
- ✅ Quota-vs-actual pacing pulls from existing dashboard metric
- ✅ Empty portfolio handling — returns zeros not errors

---

## Coordination Timeline

| Date | Event | Action |
|---|---|---|
| **2026-04-06** | Schema doc created (this document) | Deuce shares with Danny + Ian for review |
| **2026-04-10** | Phase 1 (data layer) complete | `eos_projects` table populated, custom field sync working |
| **2026-04-13** | Phase 1.5 starts | Build view + skill |
| **2026-04-16** | **Demand portfolio data starts landing** | Danny's first ABM plans in Asana |
| **2026-04-16** | Phase 1.5 deliverables complete | View live, skill works, sample output committed |
| **2026-04-22** | Phase 2 (dept meeting automation) starts | `/abm-l10-report` consumed by Sales L10 |
| **2026-04-27** | **Supply portfolio data starts landing** | Ian's first supply ABM projects |
| **2026-05-04** | First Sales L10 with full ABM report | Validation point for demand reporting |
| **2026-05-11** | First Supply L10 with full ABM report | Validation point for supply reporting |

---

## Related: 8 Dept Contexts (for All-Hands Deck Auto-Update)

The all-hands deck (master ID: `1kjg1ObSO1l15_R82w6hgQNOz8YYk3oUXPllBs-eGhow`) has 8 dept slides updated bi-weekly by the Monday cron. NOTE: This is a SUPERSET of the dept L10 contexts — Operations + Accounting/BizDev have deck slides but may not have separate L10 rituals.

```yaml
# Future addition to recess_os.yml
all_hands_deck:
  google_slides_id: "1kjg1ObSO1l15_R82w6hgQNOz8YYk3oUXPllBs-eGhow"
  cadence: bi-weekly  # Monday before Tuesday all-hands
  dept_slides:
    - id: ai_automations
      slide_title: "AI Automations"
      lead: "leo@recess.is"
      has_l10: true
    - id: product_engineering
      slide_title: "Product and Engineering"
      lead: "arbind@recess.is"
      has_l10: true
    - id: supply
      slide_title: "Supply"
      lead: "ian@recess.is"
      has_l10: true
    - id: marketing
      slide_title: "Marketing"
      lead: "courtney@recess.is"
      has_l10: true
    - id: sales
      slide_title: "Sales"
      lead: "danny@recess.is"
      has_l10: true
    - id: account_management
      slide_title: "Account Management"
      lead: "char@recess.is"
      has_l10: true
    - id: operations
      slide_title: "Operations"
      lead: "deuce@recess.is"   # Deuce (COO)
      has_l10: false  # deck-only context — folded into leadership L10
    - id: accounting_bizdev
      slide_title: "Accounting and Business Development"
      lead: "accounting@recess.is"  # Andres
      has_l10: false  # deck-only context
```

## Slide Format (canonical — matches existing deck)

Per the existing all-hands deck format, each dept slide has 3 sections:

```
[Dept Name]                                        [Recess logo]

Q2 Goals
  • Goal description (X% — $Y or count)
  • Goal description (status)
  ...

Wins from last 2 weeks
  • Win item
  • Win item
  ...

Next 2 week's focus
  • Focus item
  • Focus item
  ...
```

### Data sources per section (v1 — simplified for reliability)

| Section | Auto source | Manual override |
|---|---|---|
| Q2 Goals + progress | **BigQuery** `eos_goals` table (synced from Asana via `sync_to_bq`, includes Sunday-pushed values) | Dept lead can edit |
| Wins from last 2 weeks | **MANUAL — placeholder only in v1**. Dept lead fills in. (Q3: extract from L10 transcripts) | Dept lead fills in |
| Next 2 week's focus | **BigQuery** `eos_rocks` + upcoming MILESTONES (not tasks) due in next 14 days. Milestones only — keeps the slide short and high-signal. | Dept lead can edit |

### Why "milestones only" not tasks

Tasks are too granular for an all-hands deck. A typical dept might have 20+ open tasks but only 2-3 milestones due in the next 2 weeks. Milestones are the right grain for "what's the team focused on" — sparse and high-signal. Tasks live in Asana for the people doing the work; the deck shows the team-level commitments.

### Why "wins manual" not auto

Auto-extracting wins from L10 transcripts requires Claude inference + transcript chunking + voice-to-narrative-summarization. Each adds failure modes that can break the deck update. v1 leaves wins as a manual placeholder — dept leads have ~24 hours (Monday → Tuesday morning all-hands) to fill it in. Q3 work: revisit auto-extraction once basic flow is proven.

### BQ → Asana Goals sync flow (this enables Monday reads)

```
Sunday Goals-week cron (Phase 4):
   asana_recess_os_sync.py push_kpi_goals
   → reads BQ kpi_daily_snapshot
   → applies percentage transforms
   → POSTs to Asana Goal current_value

Daily 8am sync (Phase 1, extended):
   sync_to_bq.sync_goals_to_bq()
   → pulls all Asana Goals via API
   → writes to App_Recess_OS.eos_goals
   → captures: name, owner, current_value, target_value, % progress

Monday 8am all-hands deck cron (Phase 4):
   update_all_hands_deck reads eos_goals from BQ
   → renders dept slides (Q2 Goals section auto-filled)
   → leaves Wins section as placeholder for manual edit
   → renders Next 2 weeks from eos_rocks milestones due ≤ 14 days
```

This means the deck updater is a fast BQ reader (sub-second per slide), not a live Asana call orchestrator. By Monday, BQ has Friday's pushed values + any weekend manual edits.

The Monday bi-weekly cron produces a **DRAFT** version of the deck. Dept leads have until Tuesday morning to edit the Wins section if needed. This balances automation (zero work in steady state for goals + milestones) with human ownership (dept leads control the wins narrative).

## Schema Change Process

If this schema needs to change:
1. Update this document FIRST
2. Notify both Rock owners (Danny + Ian) via Slack DM
3. Update the `v_abm_portfolio_status` view
4. Update the `/abm-l10-report` skill if output format changes
5. Update sample output committed to repo
6. Tag commit `schema-change(abm-portfolio):` so future sessions can grep for breaking changes

**Never make a schema change without updating both Rocks' template projects to match.**

---

## Sample Output (committed to repo)

Sample outputs for both portfolios are stored at:
- `~/Projects/eos/data/sample-outputs/abm-l10-demand-2026-04-13.md`
- `~/Projects/eos/data/sample-outputs/abm-l10-supply-2026-04-13.md`

These are committed even when portfolios are empty (zero-state samples) so the format contract is visible without running BQ.
