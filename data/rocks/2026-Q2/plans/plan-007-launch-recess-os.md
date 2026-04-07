---
id: plan-007
rock_id: rock-007
title: "Execution Plan: Launch Recess OS"
owner: "deuce"
quarter: "2026-Q2"
status: active
created: "2026-04-06"
revised: ""
weeks_remaining: 8
hard_deadline: "2026-06-01"
asana_goal_id: "1213964742972565"
asana_project_id: "TBD — created in Phase 0"
---

# Execution Plan: Launch Recess OS

**Rock:** rock-007 — Launch Recess OS — AI-First EOS Operating System
**Owner:** Deuce | **Due:** Jun 1 (hard, paternity Jun 10) | **Weeks:** 8

## Architecture Summary

Three system pieces + three user-facing skills:

| Artifact | Purpose |
|---|---|
| `recess_os.py` | One Python module — every system action (sync_to_bq, push_kpi_goals, post_status, monday_pulse, refresh_meeting_card, send_preread, reconcile_actions) |
| `recess_os.yml` | One config file — every dept/meeting/goal/project mapping. References `metric_registry.py` for scorecard metric names |
| `recess_os_daily.sh` | One Cloud Scheduler entry — daily 8am Eastern. Internal day-of-week + bi-weekly parity dispatch |
| `ceos-meeting-prep` | Interactive prep skill (Mondays) — replaces both `/leadership-prep` and `/founders-prep` ideas via `--type` parameter |
| `/meeting-wrap` | End-of-meeting closed loop — 4 types: leadership / founders / dept-l10 / 1on1 |
| `/preread-fill` | Dept lead helper for filling pre-read sections |

Plus existing skills leveraged: `ceos-l10` (extended with --dept), `ceos-scorecard-autopull`, `leadership-preread`, `create-google-doc`, `ceos-rock-plans`, `ceos-rocks`, `/quick-discovery`, `/rock-status`.

## Sequencing Decisions

1. **Leadership BEFORE depts (REVISED 2026-04-07)** — leadership meetings happen this week + bi-weekly thereafter, so building leadership-first lets us validate against real upcoming meetings (Apr 9, Apr 23, May 7). Once leadership pattern is proven, dept becomes a config variant. Original plan was dept-first; user changed direction Apr 7 because the immediate leadership meeting is the natural test case.
2. **Apr 9 leadership meeting** — runs manually (system not ready). Used as first /meeting-wrap test on Apr 10.
3. **Apr 23 + May 7 leadership meetings** — first fully-automated runs.
4. **Existing Phase 0 task #1213958752431887** consolidates Recess OS Phase 0 subtasks alongside Rock owner setup tasks.

## Weekly Project Updates

| Task | Owner | Due |
|------|-------|-----|
| Project Status Update – 2026-04-11 | Deuce | Apr 11 |
| Project Status Update – 2026-04-18 | Deuce | Apr 18 |
| Project Status Update – 2026-04-25 | Deuce | Apr 25 |
| Project Status Update – 2026-05-02 | Deuce | May 2 |
| Project Status Update – 2026-05-09 | Deuce | May 9 |
| Project Status Update – 2026-05-16 | Deuce | May 16 |
| Project Status Update – 2026-05-23 | Deuce | May 23 |
| Project Status Update – 2026-05-30 | Deuce | May 30 |

## Phase 0 — Setup & Foundation (Apr 6-10)

**Outcome:** Architecture HTML page deployed, recess_os.yml configured, Asana portfolio + project + Rock file all live, plan locked. Foundation rock-solid for Phase 1 build on focus day.

| Task | Owner | Due | Depends On | Milestone |
|------|-------|-----|------------|-----------|
| **MILESTONE: Phase 0 complete — foundation ready for Phase 1 build** | Deuce | Apr 10 | — | ✓ |
| Create rock-007 file via ceos-rocks | Deuce | Apr 6 | — | Phase 0 |
| Write plan-007 (this document) | Deuce | Apr 6 | rock-007 | Phase 0 |
| Build HTML training page (`rock-5-launch-recess-os.html`) | Subagent | Apr 6 | architecture lock | Phase 0 |
| Create Asana project for Rock 5 + link to Goal 1213964742972565 | Subagent | Apr 6 | plan-007 | Phase 0 |
| Stand up Recess Projects Asana portfolio + custom fields (Project Type, Linked Rock Goal, Owner, Quarter, Status) | Deuce | Apr 7 | — | Phase 0 |
| Tag existing Asana projects with metadata (Rock-linked or not) | Deuce | Apr 8 | portfolio | Phase 0 |
| Draft `recess_os.yml` config file (goals + meetings + projects sections) | Deuce | Apr 9 | metric_registry review | Phase 0 |
| Map dept scorecard metrics from `metric_registry.py` + leadership pre-read doc into recess_os.yml | Deuce | Apr 9 | recess_os.yml | Phase 0 |
| Add Recess OS subtasks to existing Phase 0 task #1213958752431887 | Deuce | Apr 7 | — | Phase 0 |
| Create per-dept Slack channels (#sales-l10, #am-l10, #eng-l10, #marketing-l10, #supply-l10, #ai-automations-l10) | Deuce | Apr 9 | — | Phase 0 |
| Confirm 7 dept facilitator emails + members | Deuce | Apr 7 | — | Phase 0 |

**Phase 0 ends with Apr 10 focus day kickoff** — see Phase 1.

## Phase 1 — Data Layer (Apr 10 focus day → Apr 12)

**Outcome:** `recess_os.py` skeleton built, `App_Recess_OS` BQ dataset created, `sync_to_bq` running daily on Cloud Scheduler with real Asana data flowing into BQ.

| Task | Owner | Due | Depends On | Milestone |
|------|-------|-----|------------|-----------|
| **MILESTONE: Data layer live — Asana data flowing into BQ daily** | Deuce | Apr 12 | — | ✓ |
| Build `recess_os.py` module skeleton (config loader, auth init, subcommand router) | Deuce | Apr 10 | recess_os.yml | Phase 1 |
| Create `App_Recess_OS` BigQuery dataset | Deuce | Apr 10 | — | Phase 1 |
| Create BQ table schemas: eos_rocks, eos_projects, eos_goal_metric_history, eos_status_updates (single table with parent_type discriminator), eos_l10_meetings, eos_l10_action_items | Deuce | Apr 10 | dataset | Phase 1 |
| Write `sync_to_bq` subcommand (Asana → BQ for projects, tasks, **goals with current_value/target_value/percent_complete**) — enables Phase 4 deck updater to read goals from BQ instead of live Asana | Deuce | Apr 10 | recess_os.py skeleton | Phase 1 |
| Add `eos_goals` table to App_Recess_OS schema (gid, name, owner_email, current_value, target_value, percent_complete, time_period, status_text, synced_at) | Deuce | Apr 10 | dataset created | Phase 1 |
| First sync run with real data, validate row counts | Deuce | Apr 10 | sync_to_bq | Phase 1 |
| Deploy `recess_os_daily.sh` to Cloud Scheduler (daily 8am Eastern) | Deuce | Apr 10 | sync working | Phase 1 |
| Validate hourly sync cycles over Apr 11-12 weekend | Deuce | Apr 12 | cron deployed | Phase 1 |
| Update Asana intake form with Issue + Opportunity request types | Deuce | Apr 12 | — | Phase 1 |

## Phase 1.5 — ABM Reporting Layer (Apr 13-16)

**Outcome:** Shared L10 reporting infrastructure for Rock 1 (Danny — Demand ABM) and rock-005 (Ian — Supply ABM). Single BQ view + single skill, both rocks consume. Lands BEFORE demand portfolio data starts landing Apr 16.

**Why this exists:** Both ABM Rocks produce ABM plans as Asana projects in portfolios. Without a shared reporting layer, each Rock would build its own L10 reporting → duplicate work, drift, broken metrics. This phase builds it ONCE, in Recess OS, so both Rocks just consume.

**See:** `~/Projects/eos/data/architecture/abm-portfolio-schema.md` for the full schema contract.

| Task | Owner | Due | Depends On | Milestone |
|------|-------|-----|------------|-----------|
| **MILESTONE: ABM reporting layer live, both portfolios supported, sample output committed** | Deuce | Apr 16 | — | ✓ |
| Schema doc created (`abm-portfolio-schema.md`) | Deuce | Apr 6 | — | Phase 1.5 |
| Share schema doc with Danny + Ian for review | Deuce | Apr 7 | schema doc | Phase 1.5 |
| Extend `sync_to_bq` to capture Asana custom_fields_json on projects | Deuce | Apr 13 | Phase 1 complete | Phase 1.5 |
| Add `custom_fields_json STRING` column to `eos_projects` BQ table | Deuce | Apr 13 | sync extension | Phase 1.5 |
| Verify Asana custom fields land in BQ (smoke test with 1 demand portfolio project) | Deuce + Danny | Apr 14 | custom field sync | Phase 1.5 |
| Create `v_abm_portfolio_status` BQ view | Deuce | Apr 14 | custom_fields_json populated | Phase 1.5 |
| Test view returns expected rows for demand portfolio | Deuce | Apr 14 | view created | Phase 1.5 |
| Test view returns 0 rows (not error) for empty supply portfolio | Deuce | Apr 14 | view created | Phase 1.5 |
| Build `/abm-l10-report` skill | Deuce | Apr 15 | view tested | Phase 1.5 |
| Generate sample output for demand portfolio (real or zero-state) | Deuce | Apr 16 | skill working | Phase 1.5 |
| Generate sample output for supply portfolio (zero-state) | Deuce | Apr 16 | skill working | Phase 1.5 |
| Commit sample outputs to `~/Projects/eos/data/sample-outputs/` | Deuce | Apr 16 | samples generated | Phase 1.5 |
| Notify Danny + Ian that ABM L10 reporting is live | Deuce | Apr 16 | full Phase 1.5 | Phase 1.5 |

**Coordination notes:**
- Demand portfolio data starts landing **week of Apr 16** — this phase MUST land before
- Supply portfolio data starts landing **week of Apr 27** — second validation point
- Custom field naming MUST be consistent across both rocks (per schema doc)
- View handles empty portfolios gracefully (returns zeros, not errors)
- Once shipped, this becomes the canonical L10 data source for both ABM Rocks — neither Rock builds its own reporting

## Phase 2 — LEADERSHIP Meeting Automation FIRST (Apr 13-22)

**Outcome:** `ceos-leadership-prep` skill (5-round facilitated) + `/meeting-wrap --type=leadership` operational. Google Doc pre-read auto-generated via `create-google-doc` skill. Asana parent task with dept lead subtasks. Slack post to #leadership-team. Apr 23 leadership meeting partially automated. May 7 leadership meeting fully automated end-to-end. **Builds the foundation that Phase 3 (Dept) extends.**

| Task | Owner | Due | Depends On | Milestone |
|------|-------|-----|------------|-----------|
| **MILESTONE: Leadership meeting fully automated end-to-end (Apr 23 + May 7)** | Deuce | Apr 22 | — | ✓ |
| Build `ceos-leadership-prep` skill (5-round facilitated) | Deuce | Apr 14 | recess_os.yml meetings section | Phase 2 |
| Wire `leadership-preread` skill as Round 1 subroutine (scorecard auto-pull) | Deuce | Apr 14 | ceos-leadership-prep | Phase 2 |
| Build Round 2: Top of Mind capture (interactive prompts for Jack + Deuce) | Deuce | Apr 14 | skill scaffold | Phase 2 |
| Build Round 3: Decisions Pipeline capture | Deuce | Apr 15 | Round 2 | Phase 2 |
| Build Round 4: Discussion Topics generation | Deuce | Apr 15 | Round 3 | Phase 2 |
| Build Round 5: Write to Google Doc + cascade | Deuce | Apr 16 | Round 4 | Phase 2 |
| Wire `create-google-doc` skill into leadership pre-read flow (Recess brand formatting) | Deuce | Apr 16 | Round 5 | Phase 2 |
| Build Asana parent task + 7 dept lead subtasks creation logic | Deuce | Apr 17 | Round 5 | Phase 2 |
| Wire Slack post to #leadership-team (C05855AJCKF) | Deuce | Apr 17 | Asana tasks | Phase 2 |
| Wire Airtable transcript pull (last meeting context for Round 1) | Deuce | Apr 14 | daily-brief-agent client | Phase 2 |
| Build action item extraction (Fireflies field + Claude fallback) | Deuce | Apr 15 | transcript pull | Phase 2 |
| Build cross-reference logic (action items → Asana To-Dos, fuzzy semantic match) | Deuce | Apr 16 | extraction | Phase 2 |
| Build `/meeting-wrap --type=leadership` skill | Deuce | Apr 18 | full prep stack | Phase 2 |
| Run `/meeting-wrap` on Apr 9 leadership meeting transcript (post-hoc validation) | Deuce | Apr 18 | wrap skill | Phase 2 |
| Build `/preread-fill` skill (dept lead helper for filling pre-read sections) | Deuce | Apr 19 | meeting-prep skill | Phase 2 |
| Build Wednesday auto-send cron logic (24hrs before Thursday meeting) | Deuce | Apr 20 | full pre-read stack | Phase 2 |
| Apr 23 leadership meeting: first partially-automated trial | All leadership | Apr 23 | Apr 22 build complete | Phase 2 |
| Iterate based on Apr 23 trial feedback | Deuce | Apr 30 | trial feedback | Phase 2 |
| May 7 leadership meeting: first fully-automated production run | All leadership | May 7 | Apr 23 iteration | Phase 2 |
| Build `/founders-prep` Monday 9am cron (Asana card on Management board, separate from leadership) | Deuce | Apr 30 | meeting-prep skill | Phase 2 |
| First founders prep run — May 5 Monday | Deuce + Jack | May 5 | founders-prep cron | Phase 2 |

## Phase 3 — DEPT Meeting Automation (Apr 22 - May 1)

**Outcome:** Dept variants added to existing leadership-prep + meeting-wrap skills (parameterization, not new code). All 7 dept L10 contexts wired via config in `recess_os.yml`. Trial L10s with each dept lead validate the pattern. **Sales L10 + Supply L10 consume `/abm-l10-report` from Phase 1.5.**

| Task | Owner | Due | Depends On | Milestone |
|------|-------|-----|------------|-----------|
| **MILESTONE: Dept meeting automation operational across all 7 contexts** | Deuce | May 1 | — | ✓ |
| Add `--type=dept-l10` parameterization to ceos-leadership-prep skill (becomes ceos-meeting-prep) | Deuce | Apr 23 | leadership variant working | Phase 3 |
| Add `--type=dept-l10` variant to /meeting-wrap | Deuce | Apr 23 | leadership variant working | Phase 3 |
| Add per-dept config entries to recess_os.yml (Sales, AM, Eng, Marketing, Supply, AI Auto) | Deuce | Apr 24 | l10_meetings.yml schema | Phase 3 |
| Wire dept-specific scorecard slices (filter from metric_registry per dept) | Deuce | Apr 24 | recess_os.yml | Phase 3 |
| Trial run: Sales L10 with Danny | Deuce + Danny | Apr 25 | full skill stack | Phase 3 |
| Trial run: AM L10 with Char | Deuce + Char | Apr 26 | trial 1 lessons | Phase 3 |
| Trial run: Engineering L10 with Arbind | Deuce + Arbind | Apr 27 | trial 2 lessons | Phase 3 |
| Trial run: Marketing L10 with Courtney (1-person, doubles as 1:1 with Jack) | Deuce + Jack | Apr 28 | template stable | Phase 3 |
| Trial run: Supply L10 with Ian (1-person, doubles as 1:1 with Deuce) | Deuce + Ian | Apr 29 | template stable | Phase 3 |
| Trial run: AI Automations L10 with Leo (1-person, doubles as 1:1 with Deuce) | Deuce + Leo | Apr 30 | template stable | Phase 3 |
| Iterate based on dept lead feedback (across all 6 trials) | Deuce | May 1 | all trials | Phase 3 |

## Phase 4 — Goal Sync + KPI Push (May 1 - May 11)

**Outcome:** Sunday alternating cron live. All KPI Goals auto-updating from BQ. Project-backed Goals auto-updating from milestone completion. Status update narratives auto-posted. By Monday morning, BQ + Asana have fresh data for the Monday Slack pulse + leadership prep + all-hands deck updates.

| Task | Owner | Due | Depends On | Milestone |
|------|-------|-----|------------|-----------|
| **MILESTONE: Sunday cron operational, all KPI Goals auto-updating** | Deuce | May 11 | — | ✓ |
| Build `push_kpi_goals` subcommand (recess_os.py) with percentage transforms (raw / percent_higher_is_better / percent_lower_is_better) | Deuce | May 4 | recess_os.py base | Phase 4 |
| Build `post_status` subcommand (Goal + Project status updates via Asana API) | Deuce | May 5 | push_kpi_goals | Phase 4 |
| Implement ISO week parity for alternating Friday mode (goals vs projects) | Deuce | May 6 | post_status | Phase 4 |
| Wire all 3 active KPI Goals (Francisco's fulfillment time, Jack's retailer count, Deuce's NRR) | Deuce | May 7 | sync working | Phase 4 |
| Build BQ source columns for fulfillment time + retailer count (8-step KPI dashboard checklist) | Deuce + Arbind | May 9 | BQ access | Phase 4 |
| First Sunday cron run end-to-end (May 10) | Deuce | May 10 | full sync stack | Phase 4 |
| Validate Goal updates appear correctly in Asana UI | Deuce | May 9 | Friday run | Phase 4 |
| Build `monday_pulse` subcommand (Slack post to #recess-goals-kpis with dept scorecards threaded) | Deuce | May 10 | sync_to_bq | Phase 4 |
| **Build `update_all_hands_deck` subcommand** — bi-weekly Monday update of master all-hands deck (8 dept slides: AI Auto, P&E, Supply, Marketing, Sales, AM, Ops, Accounting/BizDev). Format: Q2 Goals (%) + Wins from last 2 weeks + Next 2 week's focus. Deck ID: 1kjg1ObSO1l15_R82w6hgQNOz8YYk3oUXPllBs-eGhow | Deuce | May 11 | monday_pulse | Phase 4 |
| Wire all-hands deck cron to bi-weekly parity (only on weeks with Tuesday all-hands) | Deuce | May 11 | deck updater | Phase 4 |
| Post deck link as final reply in Monday Slack thread after deck updated | Deuce | May 11 | deck updater | Phase 4 |
| First Monday pulse — May 11 | Deuce | May 11 | monday_pulse | Phase 4 |
| First all-hands deck auto-update — Monday before next bi-weekly all-hands | Deuce | May 11 | deck updater | Phase 4 |

## Phase 5 — Front Door Auto-Routing (May 11 - May 18)

**Outcome:** Asana intake form rules route incoming requests to the right skill based on type + size. Bug → /meeting-wrap-bug or QA flow, S/M → /quick-discovery, L/XL → /discovery.

| Task | Owner | Due | Depends On | Milestone |
|------|-------|-----|------------|-----------|
| **MILESTONE: Front door auto-routing operational** | Deuce | May 18 | — | ✓ |
| Add Issue + Opportunity request types to Asana intake form | Deuce | May 12 | — | Phase 5 |
| Create 5 Asana Rules (one per request type) for auto-creating discovery subtasks | Deuce | May 13 | form types | Phase 5 |
| Wire QA Session detection (multiple bugs → /qa-feedback workflow) | Deuce | May 14 | rules | Phase 5 |
| Wire size-based routing (XS/S → quick-discovery, M → light PRD, L/XL → /discovery) | Deuce | May 15 | rules | Phase 5 |
| Update Scoping Pipeline sections: Intake → Discovery → PRD → Approve → Ready | Deuce | May 16 | rules + skills | Phase 5 |
| Trial: submit one of each request type via form, validate routing | Deuce | May 17 | full pipeline | Phase 5 |
| Document the front door flow in HTML training page | Deuce | May 18 | trial validation | Phase 5 |

## Phase 6 — Hardening + Handoff (May 18 - Jun 1)

**Outcome:** Company training delivered. Team feedback survey complete. All systems documented for paternity coverage. End-to-end smoke tests pass. Comfortable buffer before paternity June 10.

| Task | Owner | Due | Depends On | Milestone |
|------|-------|-----|------------|-----------|
| **MILESTONE: Recess OS handed off, team trained, ready for paternity** | Deuce | Jun 1 | — | ✓ |
| Run end-to-end smoke test (all crons, all skills, all integrations) | Deuce | May 19 | — | Phase 6 |
| Fix any issues found in smoke test | Deuce | May 22 | smoke test | Phase 6 |
| Company training session #1 — Tuesday May 19 (architecture overview) | Deuce | May 19 | HTML page | Phase 6 |
| Company training session #2 — Tuesday May 26 (how to use it) | Deuce | May 26 | training #1 | Phase 6 |
| Run team feedback survey | Deuce | May 27 | — | Phase 6 |
| Write paternity coverage documentation (what to do if X breaks) | Deuce | May 28 | — | Phase 6 |
| Record video walkthrough of full system | Deuce | May 29 | docs | Phase 6 |
| Final hand-off meeting with Jack | Deuce + Jack | May 30 | docs + video | Phase 6 |
| Buffer day for last-minute fixes | Deuce | May 31 | — | Phase 6 |
| Recess OS officially launched + announced | All | Jun 1 | — | Phase 6 |

## Dependencies & Handoffs

| From | To | What | By When |
|------|-----|------|---------|
| Deuce | Subagent | Architecture decisions for HTML page | Apr 6 (today) |
| Deuce | Subagent | Plan file for Asana project creation | Apr 6 (today) |
| Deuce | Each Rock owner | Existing Phase 0 task subtasks | Apr 7 |
| Deuce | Each dept lead | Slack channel + scorecard metric assignments | Apr 9 |
| Each dept lead | Deuce | Trial L10 availability | Apr 18-21 |
| Deuce | Jack | Founders prep walkthrough | May 5 |
| Deuce | All leadership | Apr 23 leadership meeting (partial automation trial) | Apr 23 |
| Deuce | All leadership | May 7 leadership meeting (full automation production) | May 7 |
| Deuce | All team | Training sessions (May 19, May 26) | May 19, May 26 |
| Deuce | Jack | Final paternity hand-off meeting | May 30 |

## Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| BQ scheduled queries take time to validate | Phase 1 slips | Run sync early, validate over weekend Apr 11-12 |
| Dept lead trial scheduling | Phase 2 slips | Block 30-min slots with each dept lead in week 2 |
| /meeting-wrap edge cases | Quality issues | Test against real Apr 9 transcript first |
| Apr 23 leadership meeting fragility | Bad first impression | Have manual fallback ready |
| Deuce solo on big build | Bottleneck | Use subagents aggressively for parallel work; pull in Arbind/Leo for technical pieces |
| Phase 4 BQ KPI builds | Unknown effort | Recess-bigquery skill exists; reuse existing patterns |
| Front door routing requires Asana Rules access | Permissions delay | Verify Asana admin access early in Phase 5 |
| Paternity hard deadline | No slack | 9-day buffer Jun 1 → Jun 10 |

## Assumptions

- Deuce has bandwidth to run focus day Apr 10
- Subagents can build HTML page + Asana project in parallel today
- Existing CEOS skills (ceos-l10, ceos-rocks, ceos-scorecard-autopull, leadership-preread, create-google-doc) work as documented
- daily-brief-agent .env credentials are valid for Asana, Airtable, Slack
- BigQuery project stitchdata-384118 service account has dataset creation permissions
- Cloud Scheduler permissions match the KPI dashboard deploy setup
- Each dept lead has 30 min for trial L10 in week 2
- Apr 9 + Apr 23 + May 7 leadership meetings happen on schedule
- Jack's availability for Monday founders prep starting Apr 27

## Tracking

- **Dashboard:** Asana milestone completion % drives Goal 1213964742972565 progress bar
- **Manual:** Team feedback survey at end of Q2
- **L10 check-in:** Deuce reports on/off track weekly via Friday status updates
- **Slip rule:** If a phase milestone slips by 3 days, escalate to Jack via Asana comment + Slack DM

## Notes

- 2026-04-06: Plan created. Architecture locked through Round 1.5 facilitation (22 pieces collapsed to 6 artifacts). Subagents dispatched in parallel for HTML page + Asana project creation. Plan file written by main thread.
- 2026-04-06: Sequencing decision — DEPT meetings BEFORE leadership for higher-leverage early wins. Leadership becomes config variant.
- 2026-04-06: Hard deadline June 1 (paternity June 10, 9-day buffer).
- 2026-04-06: Existing Phase 0 task #1213958752431887 absorbs Recess OS setup work as additional subtasks (no parallel parent task).
