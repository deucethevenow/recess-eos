---
id: rock-007
title: "Launch Recess OS — AI-First EOS Operating System"
owner: "deuce"
quarter: "2026-Q2"
status: on_track
created: "2026-04-06"
due: "2026-06-01"
hard_deadline: "2026-06-01"
annual_goal: "Increase talent and operational leverage by automating EOS workflows"
kpi_target: "Recess OS operational by June 1: dept L10s automated, leadership L10 automated, /meeting-wrap closed loop live, KPI Goals auto-syncing, team feedback survey shows time savings"
asana_goal_id: "1213964742972565"
asana_project_id: "TBD — created in Phase 0"
milestones:
  - title: "Phase 0 — Setup & Foundation: HTML training page deployed, Asana portfolio stood up, recess_os.yml configured, plan locked"
    due: "2026-04-10"
    status: in_progress
  - title: "Phase 1 — Data Layer: recess_os.py module live, App_Recess_OS BQ dataset, sync_to_bq running on daily cron"
    due: "2026-04-12"
    status: todo
  - title: "Phase 1.5 — ABM Reporting Layer: shared v_abm_portfolio_status BQ view + /abm-l10-report skill, both Rock 1 (Demand ABM/Danny) and rock-005 (Supply ABM/Ian) consume"
    due: "2026-04-16"
    status: todo
  - title: "Phase 2 — LEADERSHIP Meeting Automation FIRST: ceos-leadership-prep + /meeting-wrap (leadership variant), Google Doc pre-read, Apr 23 + May 7 leadership meetings fully automated"
    due: "2026-04-22"
    status: todo
  - title: "Phase 3 — DEPT Meeting Automation: dept variant of meeting-prep + meeting-wrap, all 7 dept L10 contexts wired"
    due: "2026-05-01"
    status: todo
  - title: "Phase 4 — Goal Sync + KPI Push: Sunday alternating cron live, all KPI Goals auto-updating, percentage transforms working"
    due: "2026-05-11"
    status: todo
  - title: "Phase 5 — Front Door Auto-Routing: Asana intake form rules, request type → skill mapping, /quick-discovery + /discovery wired"
    due: "2026-05-18"
    status: todo
  - title: "Phase 6 — Hardening + Handoff: Company training delivered, team feedback survey, paternity coverage docs, end-to-end smoke tests"
    due: "2026-06-01"
    status: todo
tracking:
  type: "milestone-based + survey"
  asana_milestone_progress: "Auto-derived from Asana milestone completion %"
  manual_metric: "Team feedback survey at end of Q2 — time savings + satisfaction"
  current_baseline:
    state: "KPI Dashboard automated. CEOS skills installed. EOS guide live. ceos-rock-plans + /rock-status + /quick-discovery + asana_eos_sync.py drafted. Architecture designed and approved. Scorecards/agendas still manual. No integrated system in production yet."
  data_source: "Asana milestones + team feedback survey"
  build_needed: "recess_os.py module, recess_os.yml config, daily cron, ceos-meeting-prep skill, /meeting-wrap, /preread-fill, App_Recess_OS BQ dataset, HTML training page"
---

# Launch Recess OS — AI-First EOS Operating System

## Measurable Outcome

Recess OS is operational by June 1, 2026: Claude commands and skills automate EOS workflows — L10 meeting facilitation (company + 7 departments), scorecard auto-pull, Rock tracking, meeting agendas, KPI Goal updates, status update narratives, and pre-read distribution. Information cataloged in Recess Brain (KPIs, skills, agents, decisions). Operational data persisted in BigQuery (status updates, meeting summaries, action items, scorecard time series). Team feedback survey at end of Q2 shows measurable time savings and satisfaction improvement from automation.

## Why This Is a Company Rock

Recess is evolving into an AI-first company. Some pieces are in place (Recess Brain, KPI Dashboard, CEOS skills, ceos-rock-plans, /quick-discovery) but the system isn't connected or consistent. Manual processes for scorecards, meeting agendas, KPI pulls, and pre-read assembly waste leadership time every week. Recess OS unifies these into one system with one data layer (BigQuery), one config (recess_os.yml), and one orchestrator (recess_os.py), giving the team a working operating system that runs automatically while Deuce is on paternity leave starting June 10.

## Dependencies

- KPI Dashboard `metric_registry.py` (already built — referenced by recess_os.yml for scorecard metric definitions)
- `ceos-rock-plans` skill (already built — used to plan all 6 Q2 Rocks)
- `ceos-l10` skill (existing — extended with `--dept` parameterization)
- `ceos-scorecard-autopull` skill (existing — feeds into pre-read generation)
- `leadership-preread` skill (existing — populates Google Doc scorecard tables)
- `create-google-doc` skill (existing — Recess brand formatting)
- `daily-brief-agent/.env` (canonical third-party API credentials: Asana PAT, Airtable API key, Slack tokens)
- `daily-brief-agent/integrations/airtable_client.py` (Airtable integration pattern for Fireflies transcripts)
- BigQuery project `stitchdata-384118` (App_Recess_OS dataset to be created)
- Cloud Scheduler (single daily cron entry)
- 7 dept lead facilitator emails (ian@, danny@, char@, courtney@, leo@, jack@, deuce@ — all @recess.is)
- Per-dept Slack channels (TBD — to be created in Phase 0)
- Asana intake form (existing — rules to be added in Phase 5)
- Asana boards: Leadership Meetings, Team and 1:1 Meetings, Management (founders 1:1)

## Milestones

- [ ] **Phase 0** — Setup & Foundation (due Apr 10)
- [ ] **Phase 1** — Data Layer / sync_to_bq running (due Apr 12)
- [ ] **Phase 2** — Dept meeting automation operational (due Apr 22)
- [ ] **Phase 3** — Leadership meeting automation operational (due May 1)
- [ ] **Phase 4** — Goal sync + KPI push live (due May 11)
- [ ] **Phase 5** — Front door auto-routing live (due May 18)
- [ ] **Phase 6** — Hardening + handoff complete (due Jun 1)

## Notes

- 2026-04-06: Rock created via ceos-rocks skill. Architecture designed and locked through Round 1.5 facilitation. Plan to be created via ceos-rock-plans. HTML training page being built in parallel via subagent.
- **Hard deadline June 1** — paternity starts June 10. 9-day buffer.
- **Sequencing decision (2026-04-06):** Build dept meeting automation FIRST (Phase 2), then leadership variant (Phase 3). Higher-volume dept L10s give more leverage early. Leadership becomes a config variant of the dept pattern.
- **Apr 9 leadership meeting** — manual run (system not ready). Use to validate /meeting-wrap concept against the Fireflies transcript on Apr 10.
- **Apr 23 + May 7 leadership meetings** — first fully-automated end-to-end runs.
- **Architecture lock:** 22 pieces locked through Round 1.5 facilitation. See `~/Projects/eos/context/plans/2026-04-06-rock-5-launch-recess-os.md` for full plan.
- **Simpler architecture:** 3 system pieces (recess_os.py + recess_os.yml + daily cron) + 3 user-facing skills (ceos-meeting-prep + /meeting-wrap + /preread-fill). Down from initial 22-piece proposal — collapsed via parameterization and config-driven design.
- **Existing Phase 0 task** Asana #1213958752431887 ("Set up all Q2 2026 Rocks + KPIs/Scorecards") — Recess OS Phase 0 work added as additional subtasks under this task to consolidate.
- **Security via existing primitives:** Founders meeting uses separate Google Doc with share permissions. Sensitive BQ data stays in App_KPI_Executive (existing IAM-restricted dataset). No custom allowlist code in Q2.
