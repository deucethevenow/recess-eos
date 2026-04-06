---
id: rock-006
title: "Acquire 15 Cool Events for Sales Enablement"
owner: "ian"
quarter: "2026-Q2"
status: on_track
created: "2026-04-03"
due: "2026-06-30"
annual_goal: "Increase talent and operational leverage to gain more efficiencies"
kpi_target: "15 premium/aspirational events acquired as supply partners"
milestones:
  - title: "Ian returns to ready-to-go package (pipeline live, shortlist validated by sales, research complete)"
    due: "2026-04-17"
    status: in_progress
  - title: "3-5 evergreen venues acquired and handed to marketing/sales"
    due: "2026-05-02"
    status: todo
  - title: "10+ total events acquired (evergreen + date-specific combined)"
    due: "2026-05-30"
    status: todo
  - title: "15 events acquired, post-mortem metrics baselined"
    due: "2026-06-30"
    status: todo
tracking:
  type: "hubspot_pipeline + asana + dashboard"
  dashboard_metric: "Cool Event Acquisition funnel card on supply KPI dashboard (NEEDS BUILD)"
  manual_metric: "HubSpot 'Cool Events' pipeline board view + Asana project"
  current_baseline:
    closed_won: 1
    onboarding: 1
    sql: 1
    connected: 2
    total_pipeline_value: "$626K"
    note: "Mascot Sports/Diplo Run Club shows as Closed Won $1 from 12/20/2024 but is a historical relationship marker, not an actual acquisition — treated as a warm lead for Q2 rock purposes."
  data_source: "HubSpot Cool Events pipeline → BQ (Stitch sync) → KPI Dashboard"
  build_needed: "Level A dashboard card: X of 15 acquired + pipeline funnel by stage"
---

# Acquire 15 Cool Events for Sales Enablement

## Measurable Outcome
15 premium/aspirational events onboarded as supply partners that the sales team can use to generate brand meetings. These are events with IP and name value (e.g., Tao Group, Diplo Run Club, major festivals, exclusive brand activations) that attract cool brands. When sales can say "we have this event, would your brand want in?" it generates meetings that wouldn't happen through standard outreach.

Lagging KPI (tracked for post-mortem, not Rock scorecard): meetings booked from event-driven sales enablement outreach.

## Why This Is a Company Rock
Cool events are sales enablement tools, not standard supply inventory. They open doors for the demand side — every cool event acquired gives sales a new reason to reach out to brands. Cross-functional: Supply (Ian) acquires the events, Marketing creates enablement content after handoff (automated via HubSpot deal card → Slack → Asana), Sales (Andy, Katie, Danny) uses them to generate brand meetings. Jack provides strategic direction on which events carry the most brand cachet.

## Dependencies
- Sales team (Andy, Katie, Jack, Danny) validating event priority — "which of these would actually help you book a meeting?"
- Marketing creating enablement content after each event is acquired (already automated handoff)
- Leo building KPI Dashboard card for pipeline visibility
- Leo building event acquisition framework/skill for repeatable subtask template

## Milestones
- [ ] Ian returns to ready-to-go package — pipeline, research, sales-validated shortlist (Apr 17)
- [ ] 3-5 evergreen venues acquired and handed to marketing/sales (May 2)
- [ ] 10+ total events acquired — evergreen + date-specific combined (May 30)
- [ ] 15 events acquired, post-mortem metrics baselined (Jun 30)

## Two Event Types

| Type | Description | Urgency | Examples |
|------|-------------|---------|----------|
| **Evergreen** | Always-on venues/brands, no specific event date | Acquire anytime, sales can use immediately | Tao Group, Diplo Run Club, Surf Lodge, Palm Tree Club |
| **Date-Specific** | Happens on specific dates, needs lead time | Must acquire 6-8 weeks before event for sales to use | Lollapalooza, Governors Ball, Art Basel, F1 Miami |

Sequencing logic: Evergreen first (fast wins, no timing constraint), then date-specific events sequenced by event date minus 6-8 weeks lead time. Events happening Jul-Dec 2026 are the sweet spot for Q2 acquisition work.

## Architecture

### Asana = The Hunting Tracker
- Project: "Q2 2026 — Cool Event Acquisition"
- Each target event = a milestone task with subtasks for the acquisition workflow
- Subtasks: Event research + universe mapping → Contact intel + find decision maker → Outreach sequence launched → Follow-up / alternate paths → Terms negotiation → Onboard on platform → Marketing handoff
- Sections for pipeline visibility

### HubSpot = The Sales Pipeline (Contact-Level)
- Pipeline: "Cool Events" (ALREADY LIVE as of Apr 3)
- Stages: Connected → Meeting Booked → SQL (qualified, logistics work) → Onboarding → Closed Won
- Deals only enter pipeline when a real contact responds/connects
- Deal card: Event name, amount, contact, custom terms

### KPI Dashboard = Visibility
- Level A card: Big number (X of 15 acquired) + pipeline funnel by stage
- BQ query against HubSpot Cool Events pipeline (Stitch sync)

## Pipeline Status (as of Apr 3, 2026)

| Stage | Count | Deals |
|-------|-------|-------|
| Connected | 2 | Raspatello+Co (North Coast Music Fest), FSO (Food Access LA / Cinespia) |
| Meeting Booked | 0 | — |
| SQL | 1 | Tixr Inc (corporate partnership — higher-level play) |
| Onboarding | 1 | Audacy ($500K) |
| Closed Won | 1 | TAO Group - Cabanas ($126K, contact: Jenna Levi) |
| Warm Lead (historical marker, not acquired) | 1 | Mascot Sports/Diplo Run Club ($1 from 12/20/2024 — relationship only, needs real acquisition in Q2) |

## Warm Leads & Flags
- **Palm Tree Crew** — warm intro, Ian knows the people
- **cam@medium-rare.com** — warm, knows Jack, does cool events, reached out for one-offs
- ⚠️ **tyler.middendorf@1iota.com (1iota/Tixr event)** — DO NOT outreach, Tixr corporate conversation in progress

## Notes
- 2026-04-03: Rock created. Ian OOO Apr 6-17. Deuce + Leo prep during OOO.
- 1 of 15 actually Closed Won (Tao Group $126K) — rock starts at ~7% done.
- Diplo Run Club ($1 historical marker from 12/20/2024) is a warm lead, NOT an acquisition — needs real close in Q2.
- Audacy at $500K in Onboarding could be next acquisition.
- Target list: 98 events across 13 categories (55 from Jack's original list + 43 AI research additions). Google Sheet for prioritization: https://docs.google.com/spreadsheets/d/1FNdgbXIEY5kDetKmnCBpSGEE0rub3qmAp0R6uGPF5ak
- Post-acquisition handoff already automated: HubSpot deal card → Slack notification to marketing → Asana card → weekly AM/Sales/Supply Needs Meeting.
- Custom terms are the norm for cool events — non-standard pricing, flexible minimums. Only hard requirement: model fit (they need staff to distribute).

## References
- Discovery: Cool Event Acquisition for Sales Enablement — https://www.notion.so/teamrecess/33778d863acd81059facdcee821a183b
- Discovery: Supply ABM Category Playbook Framework — https://www.notion.so/teamrecess/33578d863acd81a1b0c8eb120ef7d1c2
- Target list Google Sheet: https://docs.google.com/spreadsheets/d/1FNdgbXIEY5kDetKmnCBpSGEE0rub3qmAp0R6uGPF5ak
- HubSpot Pipeline: Cool Events (Pipeline view in HubSpot Deals)
