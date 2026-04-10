---
id: rock-004
title: "Set Dept AI Levels and Roadmap for Automations"
owner: "deuce"
quarter: "2026-Q2"
status: on_track
created: "2026-03-23"
revised: "2026-04-09"
due: "2026-05-29"
original_due: "2026-06-30"
hard_deadline_reason: "Deuce paternity leave starts 2026-06-01; pulled in from Jun 30 with 3-day buffer (Sat-Sun-Mon before Jun 1)"
annual_goal: "Increase talent and operational leverage to gain more efficiencies"
kpi_target: "Plans created per dept, AI levels defined, features identified, estimated time + $ savings"
plan_file: "plans/plan-004-dept-ai-roadmaps.md"
asana_project: "https://app.asana.com/1/21487286163067/project/1213994448499352"
notion_hub: "https://www.notion.so/AI-Readiness-Assessments-33a78d863acd81a4b4e0c5ce872e5dec"
milestones:
  - title: "Phase 0 — AM pilot complete, AM roadmap + hire spec ready for Apr 20-24 in-person meeting"
    due: "2026-04-17"
    status: in_progress
  - title: "Phase I — In-person AM review held Tue Apr 22; AM Q3 picks locked; hire decision made; AM execution started in Asana"
    due: "2026-04-24"
    status: todo
  - title: "Phase II — All 7 remaining departments assessed and scored (async self-serve)"
    due: "2026-05-08"
    status: todo
  - title: "Phase III — All 8 roadmaps generated; cross-dept synthesis + Leo capacity check; Asana architecture designed; leadership pre-read distributed"
    due: "2026-05-15"
    status: todo
  - title: "Phase IV — Full leadership review + Q3 picks locked across all depts; converted to Asana; Rock closed"
    due: "2026-05-29"
    status: todo
tracking:
  type: "manual"
  dashboard_metric: "None needed — deliverable-based"
  manual_metric: "Asana milestones in the Rock 4 execution project (5 phase milestones) + Notion Roadmaps DB row count (target: 9 rows = 8 dept roadmaps + 1 cross-dept rollup)"
  current_baseline:
    plans_created: 0
    state: "No set plans. Individual experiments but no structured department-level roadmaps."
  data_source: "Asana execution project (Q2 2026 Rock 4) + Notion AI Readiness Assessments DBs"
  build_needed: "Done — tooling built, Notion DBs live, Asana execution project populated"
---

# Set Dept AI Levels and Roadmap for Automations

## Measurable Outcome
Every department has a defined AI maturity level (1-5 using the Digital Operations Playbook framework), a documented roadmap of automation opportunities with sequencing for Q3, and estimated time + dollar savings for each initiative. This becomes the investment roadmap for H2 2026.

## Why This Is a Company Rock
Upfront AI investments now prevent adding headcount later. Each department has untapped automation potential, but without a structured assessment and plan, efforts are ad-hoc. This Rock creates the blueprint for operational leverage across the company.

## Approach

A 3-skill pipeline (installed via Recess-Brain-V2) does the work end-to-end:
1. **`ai-readiness-assess`** — Each team member self-serves a 25-min conversational interview on their own machine (no Deuce facilitation)
2. **`ai-readiness-score`** — Deuce synthesizes per-person files into a department-level diagnostic per dept
3. **`ai-readiness-roadmap`** — Deuce generates prioritized, sequenced roadmap using RICE + foundation-first framework; Asana conversion via `ceos-rock-plans`

**Source framework:** Greenberg & White, *Digital Operations Playbook* — 5 Levels + 5 Pillars + 30-question self-assessment.

**Working principle:** Batch Deuce's work into 2-3 hour focused blocks, not 30-min daily tasks. Self-serve removes Deuce from team interviews entirely.

## Departments In Scope (8)

**Tier 1 — full assessments:**
1. Sales (Danny + AEs)
2. Account Management (Char + team) — **PILOT dept**
3. Supply (Ian + team)
4. Marketing (Courtney)
5. Engineering (Arbind + team)

**Tier 2 — handled in single combined session due to small size:**
6. Operations
7. Accounting (Deuce assesses on behalf during Phase 0; new hire ramped later)
8. Administrative

**Leo (AI Automations) is NOT a department.** Leo is a cross-functional advisor who reviews automation feasibility for every dept and is the likely implementer of approved AI/automation picks across departments.

## Two Leadership Touchpoints

1. **In-person AM-only review — Tue Apr 22, 2026** — Drives the AM Q3 lock and hire decision. AM execution starts immediately after, giving AM a 5-week head start on the rest of the company.
2. **Full company leadership review — Mon May 18 OR Tue May 19, 2026** — Jack + leadership team locks Q3 picks across all 8 departments. Forces the Leo capacity trade-off conversation in person.

## Dependencies
- Each department team self-serving the assessment (async, ~25 min per person, ~18 people total)
- Char availability for 45-min 1:1 review Fri Apr 17
- In-person meeting happening Tue Apr 22 with right attendees
- Jack + leadership availability Mon-Tue May 18-19 for final review
- Leo's Q3 capacity for the automation work selected

## Milestones (5 phases)
- [ ] **Phase 0** — AM pilot complete, AM roadmap + hire spec ready for Apr 20-24 meeting — due Fri Apr 17
- [ ] **Phase I** — AM Q3 picks locked + hire decision + AM execution started in Asana — due Fri Apr 24
- [ ] **Phase II** — All 7 remaining departments assessed and scored — due Fri May 8
- [ ] **Phase III** — All 8 roadmaps + cross-dept synthesis + Asana architecture + leadership pre-read — due Fri May 15
- [ ] **Phase IV** — Full leadership lock + Asana conversion + Rock closed — due **Fri May 29**

## Execution Artifacts

| Artifact | Location |
|---|---|
| Execution plan | `~/Projects/eos/data/rocks/2026-Q2/plans/plan-004-dept-ai-roadmaps.md` (312 lines) |
| Asana execution project (61 tasks) | https://app.asana.com/1/21487286163067/project/1213994448499352 |
| Asana overview project (pipeline reference) | https://app.asana.com/1/21487286163067/project/1210663617324858 |
| Notion hub | https://www.notion.so/AI-Readiness-Assessments-33a78d863acd81a4b4e0c5ce872e5dec |
| Skills | `~/Projects/Recess-Brain-V2/skills/ai-readiness-{assess,score,roadmap}/` |
| Data files | `~/Projects/Recess-Brain-V2/data/ai-assessments/<dept>/<person>.md` |
| Notion config (DB IDs) | `~/Projects/Recess-Brain-V2/data/ai-assessments/.notion-config.json` |

## Notes

- **2026-03-23:** Rock created. No structured plans exist today. Some individual experiments (Recess Brain, Claude skills) but not department-level.
- **2026-04-06:** Tooling complete — 3 skills built (`ai-readiness-assess`, `ai-readiness-score`, `ai-readiness-roadmap`), Python parser scripts, reference docs. Notion parent page + 3 databases (Personal Assessments, Department Diagnostics, Roadmaps) created and smoke-tested. Sibling Asana project "AI Automations Roadmap" populated with full pipeline overview.
- **2026-04-06:** Due date pulled in from original Jun 30 → **Fri May 29** to fit paternity leave starting Jun 1. 3-day buffer (Sat-Sun-Mon). Milestone structure restructured from 4 outcome-based to 5 phase-based milestones matching the execution plan.
- **2026-04-06:** Execution plan file written at `plans/plan-004-dept-ai-roadmaps.md` via `ceos-rock-plans` skill (all 5 rounds). 61 tasks across 5 phases, 5 milestones, 40 dependencies wired.
- **2026-04-09:** New Asana execution project `Q2 2026 Rock 4 — Set Dept AI Levels & Roadmap` (gid `1213994448499352`) created with 61 tasks + 5 milestones + 40 dependencies wired + sections per phase. 4 Phase 0 tasks already marked complete (tooling build, Notion DB creation, wiring, sibling project overview).
- **Working principle:** Batch Deuce's work into 2-3 hour focused blocks. Async self-serve removes Deuce from team interviews entirely. Two leadership touchpoints (Apr 22 in-person AM, May 18-19 full company) are the high-leverage decision moments.
- **Next action (Thu Apr 9):** (1) Run `ai-readiness-assess` on yourself for accounting to validate the skill. (2) Once confirmed, send Slack to Char + Francisco + Ashton + Victoria + Claire announcing the AM self-serve window with deadline EOD Wed Apr 15.
