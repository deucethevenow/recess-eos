---
id: plan-005
rock_id: rock-005
title: "Execution Plan: Achieve Q2 Key Supply Target Moment Goals"
owner: "ian"
quarter: "2026-Q2"
status: active
created: "2026-04-01"
revised: "2026-04-10"
weeks_remaining: 13
---

# Execution Plan: Achieve Q2 Key Supply Target Moment Goals

**Rock:** rock-005 — Achieve Q2 Key Supply Target Moment Goals
**Owner:** Ian (Supply AE) | **Due:** Jun 30 | **Weeks:** 13

## Weekly Project Updates

| Task | Owner | Due |
|------|-------|-----|
| Project Status Update – 2026-04-04 | Ian | Apr 4 |
| Project Status Update – 2026-04-11 | Ian | Apr 11 |
| Project Status Update – 2026-04-18 | Ian | Apr 18 |
| Project Status Update – 2026-04-25 | Ian | Apr 25 |
| Project Status Update – 2026-05-02 | Ian | May 2 |
| Project Status Update – 2026-05-09 | Ian | May 9 |
| Project Status Update – 2026-05-16 | Ian | May 16 |
| Project Status Update – 2026-05-23 | Ian | May 23 |
| Project Status Update – 2026-05-30 | Ian | May 30 |
| Project Status Update – 2026-06-06 | Ian | Jun 6 |
| Project Status Update – 2026-06-13 | Ian | Jun 13 |
| Project Status Update – 2026-06-20 | Ian | Jun 20 |
| Project Status Update – 2026-06-27 | Ian | Jun 27 |

Weekly Status Update Description:
```
Weekly Project Status Update

Please include:
1. What's been accomplished since the last update?
2. What's currently blocked?
3. What's next?
4. Overall status: On Track / At Risk / Off Track
```

## Phase 0 – Setup & Governance

| Task | Owner | Due | Depends On | Milestone |
|------|-------|-----|------------|-----------|
| **MILESTONE: Project infrastructure ready** | Deuce | Apr 7 | — | ✓ |
| Create Asana project with all sections (Weekly Updates, Phase 0-IV) | Deuce | Apr 3 | — | Phase 0 |
| Confirm Q2 targets with Ian (same as Q1 sub-goals + holiday_lights_drive_thru) | Ian | Apr 3 | — | Phase 0 |
| Agree on category launch priority order with Ian | Deuce | Apr 4 | Targets confirmed | Phase 0 |
| Add collaborators (Ian, Leo, Arbind, Deuce, Courtney) | Deuce | — | Project created | Phase 0 |
| Populate Project Overview (goal, baseline Q1 %, RACI, Notion discovery links) | Deuce | — | Project created | Phase 0 |
| Kick off in Slack — announce Rock, owners, timeline, weekly cadence | Deuce | Apr 7 | — | Phase 0 |

## Phase I – Infrastructure Build (Weeks 1-3)

| Task | Owner | Due | Depends On | Milestone |
|------|-------|-----|------------|-----------|
| **MILESTONE: Live retailer inventory on dashboard + playbook template operational** | Leo | Apr 21 | — | ✓ |

### Track A: KPI Dashboard + Data Pipeline

| Task | Owner | Due | Depends On | Milestone |
|------|-------|-----|------------|-----------|
| Expose retailer alignment data from Recess platform to BigQuery | Arbind | Apr 11 | — | Phase I |
| Document retailer alignment scoring methodology (what makes a listing "Walmart-indexed" vs "CVS-indexed") | Arbind | Apr 11 | — | Phase I |
| Build BQ aggregation view: primary_type x retailer x reach (replaces manual Google Sheet) | Leo | Apr 14 | Platform data in BQ | Phase I |
| Build "Retailer Audience Inventory" section on supply KPI dashboard — matrix table + goal progress bars | Leo | Apr 18 | BQ view ready | Phase I |
| Wire Q2 goal targets into dashboard (current reach vs target per type, auto-calculated %) | Leo | Apr 21 | Dashboard section live | Phase I |
| Validate dashboard numbers against manual Google Sheet — sanity check with Ian | Ian | Apr 21 | Dashboard live | Phase I |

### Track B: Category Playbook Framework

| Task | Owner | Due | Depends On | Milestone |
|------|-------|-----|------------|-----------|
| Create HubSpot custom properties: supply_category, supply_tier, supply_type, supply_dri, supply_phase | Leo | Apr 7 | — | Phase I |
| Create Notion workspace: Categories DB, Accounts DB, Industry Research DB | Leo | Apr 11 | — | Phase I |
| Build Category Playbook template (8 sections: landscape, value prop, accounts, personas, channels, marketing, execution, reporting) | Leo | Apr 14 | Notion workspace | Phase I |
| Build Account Brief templates (L&E, Win Back, Net New) | Leo | Apr 14 | Notion workspace | Phase I |
| Create App_Supply_ABM BigQuery dataset + core tables | Leo | Apr 11 | — | Phase I |
| Build /launch-category skill (core thought-partner flow — 7-phase lifecycle) | Leo | Apr 18 | Templates + BQ ready | Phase I |
| Test /launch-category on university_housing as pilot run | Leo + Ian | Apr 21 | Skill built | Phase I |

## Phase II – Category Launches (Weeks 4-10)

Each category is its own milestone. Per-category lifecycle (~1 week):
1. Industry research + account universe + tiering (Ian + Leo, 1-2 hrs)
2. Contact intel + Tier 1 account briefs (Ian, 1-2 days)
3. Execution setup + outbound sequences live (Ian + Leo, 1 day)
4. Marketing handoff → Courtney builds category marketing plan (parallel)

### Category Milestones

| # | Category | Target | Due | Q1 Baseline | Subtasks |
|---|----------|--------|-----|-------------|----------|
| 1 | **university_housing** | 1M National | Apr 25 | 66% | Research + tiering, Contact intel + briefs, Execution + outbound, Conference follow-up (300+ complexes), Marketing plan (Courtney, Apr 28) |
| 2 | **youth_sports** | 1M Nat'l + 500k WMT | May 2 | 69% | Research + tiering, Contact intel + execution, Marketing plan (Courtney, May 5) |
| 3 | **veterinary_clinic** | 500k National | May 9 | 61% | Research + tiering, Contact intel + execution, Marketing plan (Courtney, May 12) |
| 4 | **fitness_studio** | 500k Walmart | May 16 | 52% | Research + tiering, Contact intel + execution, Marketing plan (Courtney, May 19) |
| 5 | **kids_camp** | 1M National | May 23 | 10% | Research + tiering, Contact intel + execution, Marketing plan (Courtney, May 26) |
| 6 | **social_sports** | 1M top 30 DMAs | May 30 | 21% | Research + tiering, Contact intel + execution, Marketing plan (Courtney, Jun 2) |
| 7 | **campground_glampgrounds** | 500k National | Jun 6 | 0% | Research + tiering, Contact intel + execution, Marketing plan (Courtney, Jun 9) |
| 8 | **holiday_lights_drive_thru** | 1M National | Jun 13 | NEW | Research + tiering, Contact intel + execution, Marketing plan (Courtney, Jun 16) |

### Infrastructure (supports all categories)

| Task | Owner | Due |
|------|-------|-----|
| Build /category-marketing-plan skill | Leo | Apr 21 |

## Phase III – Pacing Checkpoint (Week 8)

| Task | Owner | Due | Depends On | Milestone |
|------|-------|-----|------------|-----------|
| **MILESTONE: 3 of 8 supply types at 100% of Q2 target** | Ian | May 27 | — | ✓ |
| Pull dashboard snapshot: how many types at 100%? | Ian | May 27 | Dashboard live | Phase III |
| Identify at-risk categories (below 75% of target) | Ian | May 27 | Snapshot | Phase III |
| If <3 at goal: create recovery plan for lagging types — what changes? | Ian + Deuce | May 30 | Assessment | Phase III |
| Report pacing status in L10 | Ian | May 27 | — | Phase III |

## Phase IV – Retrospective + Rock Scoring (Jun 30)

| Task | Owner | Due | Depends On | Milestone |
|------|-------|-----|------------|-----------|
| **MILESTONE: 5 of 8 supply types at 100% of Q2 target** | Ian | Jun 30 | — | ✓ |
| Rock scoring: count types at goal, document what worked and what didn't | Ian + Deuce | Jun 30 | — | Phase IV |
| Document category playbook learnings for Q3 (what to repeat, what to change) | Ian | Jun 30 | — | Phase IV |

## Dependencies & Handoffs

| From | To | What | By When |
|------|-----|------|---------|
| Arbind | Leo | Retailer alignment data exposed in BigQuery | Apr 11 |
| Arbind | Leo | Scoring methodology documentation | Apr 11 |
| Leo | Ian | Dashboard live with retailer inventory section | Apr 18 |
| Leo | Ian | /launch-category skill ready to use | Apr 18 |
| Leo | Courtney | /category-marketing-plan skill ready to use | Apr 21 |
| Ian | Courtney | Category launched (research + accounts done) → marketing handoff | Each category week |
| Courtney | Ian | Marketing plan + campaigns executing per category | 1 week after handoff |
| Ian | Deuce | Weekly status updates for L10 reporting | Every Friday |

## Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Arbind can't deliver platform data by Apr 11 | Phase I delayed → all category launches slip | Deuce to escalate in L10; fallback: use manual Google Sheet data as interim BQ source |
| University housing conference pipeline doesn't convert | UH stays at 66% despite being "easy win" | Ian to follow up aggressively on 300+ complexes; set weekly conversion targets |
| Courtney bandwidth split across 3 Rocks (supply ABM, demand ABM, A2) | Marketing plans lag behind category launches | Prioritize marketing for categories closest to goal; Tier 2/3 categories get template-only marketing |
| Category playbook takes longer than 1 week per category | Schedule compresses, later categories rushed | Front-load the hardest research; simplify later categories by reusing patterns from early ones |
| Some categories (campgrounds 0%, kids_camp 10%) may be structurally hard | Miss the "5 of 8" target | Focus on locking in 5 quick wins first; treat hardest categories as stretch goals |

## Assumptions
- Q2 targets are the same numbers as Q1 (confirmed by user Apr 1)
- Q1 progress carries forward — not starting from zero
- University housing will accelerate due to 300+ complexes from recent conference (~180-200k reach by end of April)
- Courtney's supply ABM marketing execution is her core Rock contribution (alongside demand ABM for Danny)
- Signal detection / monitoring system is out of scope for Q2 — future quarter work
- Leo has bandwidth for both KPI dashboard build and category playbook framework in parallel (weeks 1-3)
- Arbind can prioritize the retailer alignment data pipeline by Apr 11
- Ian can realistically launch 1 category per week while also managing ongoing outbound on prior categories

## Tracking

- **Dashboard:** Retailer Audience Inventory section on supply KPI dashboard (live after Apr 21)
- **Manual (interim):** Asana sub-goals with 8 connected sub-goals and % progress
- **L10 check-in:** Ian reports on/off track weekly
- **Slip rule:** If a task slips twice, flag as milestone risk in next Weekly Status Update

## Out of Scope (Q3+)
- Signal detection infrastructure (stale account alerts, engagement spike notifications)
- Automated trigger-based follow-ups
- Make.com workflows for cross-tool automation
- Slack alerts on goal threshold crossings
- Goal forecasting / trajectory prediction
- "What-if" simulator for inventory changes
- Retailer affinity scoring beyond binary alignment

## References
- Discovery: Retail Audience Inventory Reporting — https://www.notion.so/teamrecess/33478d863acd81db9acddfb64f172086
- Discovery: Supply ABM Category Playbook Framework — https://www.notion.so/teamrecess/33578d863acd81a1b0c8eb120ef7d1c2
- Current tracking sheet: https://docs.google.com/spreadsheets/d/1QyMnRRxbMmAsFNwlP2VgAo3FtDvmJYjwCvupgzcNYns/edit
- Asana Q1 Goal: https://app.asana.com/0/goal/1213622658666824
- Supply KPI Dashboard: https://kpi-dashboard-687073027146.us-central1.run.app/supply
