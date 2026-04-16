---
id: rock-008
title: "Onboard New ProServ Vendors — Reduce Service Costs"
owner: "claire"
quarter: "2026-Q2"
status: on_track
created: "2026-04-09"
due: "2026-06-30"
annual_goal: "Take Rate 49%+ (reduce ProServ cost of goods sold)"
kpi_target: "11-12 new ProServ vendors onboarded across shipping (3), overwrap (1-2), printing (4), warehouse (3) — ALL cheaper than incumbents + ≥4 with API capability (≥1 shipping + ≥1 printing) — by June 30"
milestones:
  - title: "Baseline established + 60-candidate pipeline sourced (Phase 0 + I)"
    due: "2026-04-21"
    status: todo
  - title: "All RFPs sent via HubSpot sequences + all responses collected (Phase II)"
    due: "2026-05-12"
    status: todo
  - title: "11-12 finalists selected via Team Review Call + platform workflow agreed + API/WMS docs collected (Phase III)"
    due: "2026-06-02"
    status: todo
  - title: "All vendors listed on platform + Master Vendor Capability Checklist published + team trained + Q3 API Integration Rock scoping memo handed off (Phase IV)"
    due: "2026-06-16"
    status: todo
tracking:
  type: "manual + dashboard"
  dashboard_metric: "Take Rate (KPI dashboard — lagging indicator, impact arrives Q3)"
  manual_metric: "Vendor count by phase + cost delta % per category — tracked in Master Google Sheet + Asana Project"
  current_baseline:
    shipping_vendors: "1 API-integrated (Unishippers) + manual others"
    overwrapping_vendors: "1"
    printing_vendors: "limited pool for 4x6 + pull-up banners"
    warehouse_vendors: "0 decoupled partners"
    cost_baseline: "TBD — incumbents re-quote Reference Shipment Spec in Phase I by Apr 21"
asana_goal_id: "1213964743621568"
asana_project_id: "1213987713544324"
collaborators:
  - francisco
  - char
  - deuce
attachments:
  - path: "data/rocks/2026-Q2/plans/plan-008-proserv-vendors.md"
    label: "Execution plan (5 phases, 40 tasks, dependencies wired)"
---

# Onboard New ProServ Vendors — Reduce Service Costs

## Measurable Outcome

By **June 30, 2026**, Recess has **11-12 new ProServ vendors onboarded** — each **cheaper than all current incumbents** in their category — and listed on the Recess platform with agreed manual-quoting workflow:

- **Shipping: 3 vendors** (≥1 with API, all cheaper than existing partners, with WMS system named + WMS integration docs collected)
- **Overwrapping: 1 required + 1 stretch** (cheaper than incumbent; API not required)
- **Printing: 4 vendors** (2× 4x6 cards + 2× pull-up banners; cheaper than incumbents; ≥1 with API + placement integration; rate cards with volume tiers + variable-data pricing confirmed; 3rd-party label acceptance confirmed)
- **Warehouse: 3 vendors** (rate card + Unishippers compatibility + decoupling from shipping confirmed)

**Supporting deliverables:**
- Master Vendor Capability Checklist published (operating procedure for manual quoting for next 3-6 months)
- Cost reduction % calculated per category against baseline
- API + WMS documentation collected as raw material for Q3 API Integration Rock
- Team trained live on new vendors + manual quoting workflow

**NOT in scope:** Wiring any API integrations into the Recess platform. The "Get Quote" rate-comparison button is an MVP prototype and is not relied upon in this Rock. All quoting in Q2 is manual via Google/Excel docs. API integration is deferred to a Q3 Rock.

## Milestones

- [ ] **Apr 21 — Baseline established + 60-candidate pipeline sourced** (Phase 0 + I)
  - Reference Shipment Spec v1 built
  - Incumbent vendors re-quote against spec → baseline benchmark doc published
  - 60+ new candidates (24 shipping + 15 printing + 6 overwrap + 15 warehouse) sourced by Francisco into Master Google Sheet
  - HubSpot CRM ProSVC contacts pulled into tracker
- [ ] **May 12 — All RFPs sent + responses collected** (Phase II)
  - 4 HubSpot 4-step sequences built (Char-approved for brand voice)
  - All candidates enrolled in their category sequence
  - Status check calls held with Francisco (Apr 25 kickoff + May 5 mid-point + May 12 cutoff)
  - All responses in tracker or marked dropped; qualified candidates tagged for Phase III
- [ ] **Jun 2 — Finalists selected + platform workflow agreed** (Phase III)
  - All categories vetted against cost baseline + category-specific criteria
  - Team Finalist Review Call held May 27 (Claire + Francisco + Char + Deuce)
  - 11-12 finalists selected (3 shipping ≥1 API + 1-2 overwrap + 4 printing ≥1 API/placement + 3 warehouse)
  - API quoting docs + WMS system names + WMS integration docs + printing API/placement docs collected → shared folder
- [ ] **Jun 16 — Vendors activated + documented + Q3 handoff** (Phase IV)
  - All 11-12 finalists listed on Recess platform
  - Manual quoting process documented per category → team wiki
  - Cost reduction % calculated per category
  - Master Vendor Capability Checklist published (Google Sheet end file)
  - Live team training session held (recorded for async)
  - Rock completion memo drafted
  - Q3 API Integration Rock scoping memo drafted + handoff meeting held with Char + Deuce

## Why This Is a Company Rock

Sales is flagging ProServ costs as too high and consuming proposal budgets. The current vendor pool is **structurally limited** — 1 API shipping vendor and 1 overwrapping vendor means no real competition and no leverage to drive cost down. **Expanding the vendor pool is the highest-leverage action available** to reduce ProServ cost of goods and improve Take Rate (the V/TO 1-Year Plan target).

This is cross-functional: **AMs** flagged the pain, **Sales** benefits from improved proposal margins, **AC team** consumes the new vendors daily via the documented manual quoting process, **Supply / Operations** gains the warehouse decoupling leverage, and **Engineering (Q3)** receives the API/WMS documentation as raw material for platform automation. Claire owns it as the person closest to the daily AC workflow. Francisco partners on lead-gen (the heaviest front-loaded piece). Char gates brand voice on the HubSpot sequences and contributes commercial judgment at finalist selection. Deuce joins finalist selection for strategic concentration checks and receives the Q3 handoff.

## Dependencies

- **Francisco's capacity** — ~12 hours front-loaded over Weeks 1-2 for lead-gen (60 candidates). Single biggest execution risk (R1 in the plan).
- **Char's capacity** — ~30 min Apr 23 for HubSpot sequence review + 60 min May 27 Team Finalist Review Call
- **Deuce's capacity** — 60 min May 27 Team Finalist Review Call + 60 min Jun 16 Q3 handoff meeting
- **Incumbent cooperation** — incumbent vendors must re-quote Reference Shipment Spec for baseline (Phase I)
- **HubSpot sequence infrastructure** — existing HubSpot Sequences product must accept procurement-style cadences
- **Platform vendor listing flow** — assumed production-live per discovery; all manual quoting, no reliance on the MVP "Get Quote" button

## Notes

- 2026-04-09: Rock created. Scope locked via 5-round facilitation with Deuce (2026-04-08). Execution plan `plan-008-proserv-vendors.md` written + Asana project `1213987713544324` deployed + Asana Goal `1213964743621568` updated (Claire as owner, 0→11 metric, Q2 time period) + 40 parent tasks with structured descriptions + 36 dependencies wired + 10 weekly status tasks created + 4 project members added (Claire, Francisco, Char, Deuce).
- 2026-04-09: Initial ID collision — Arbind's AI Harness Rock briefly held rock-008 in the morning. Resolved by reassigning AI Harness to rock-009 and letting this Rock reclaim rock-008 (conceptually the slot it held via the Asana Goal placeholder created in March). Plan file is `plan-008-proserv-vendors.md`.
- 2026-04-09: Discovery source — `recess-prd/01_DISCOVERY/professional-services/` (AM-led ProSVC workflow discovery dated Mar 30, 2026).
- 2026-04-09: Claire owns 1 Q2 Rock — below EOS 3-7 guidance but intentional per Deuce (not flagged as issue).
