# App_Recess_OS — BigQuery Dataset

Central data hub for Recess OS. Synced from Asana hourly via `scripts/asana_eos_sync.py`.

## Tables (synced from Asana)

| Table | Source | Contents |
|-------|--------|----------|
| `eos_rocks` | Asana Goals | Rock definitions, owners, status, progress % |
| `eos_rock_tasks` | Asana Tasks | Individual tasks within Rock projects |
| `eos_pipeline_items` | Scoping Pipeline | All pipeline items with stage + age |
| `eos_issues` | Pipeline (filtered) | Issues and Opportunities only |
| `eos_todos` | To-Do Project | Weekly To-Dos and completion status |

## Views (computed)

| View | Purpose |
|------|---------|
| `v_rock_health` | On / At Risk / Off Track per Rock |
| `v_project_status` | Completion %, velocity, blockers per project |
| `v_quarterly_summary` | Cross-Rock executive summary |

## Setup

```bash
# Create the dataset
bq mk --dataset stitchdata-384118:App_Recess_OS

# Run initial sync
ASANA_ACCESS_TOKEN=xxx python3 scripts/asana_eos_sync.py

# Create views
ASANA_ACCESS_TOKEN=xxx python3 scripts/asana_eos_sync.py --create-views
```

## Cloud Scheduler (hourly)

```bash
# Deploy sync as Cloud Function or Cloud Run job, then schedule:
gcloud scheduler jobs create http asana-eos-sync \
  --schedule="7 * * * *" \
  --uri="https://[CLOUD_RUN_URL]/sync" \
  --http-method=POST \
  --time-zone="America/Denver"
```
