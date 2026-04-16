---
id: plan-008
rock_id: rock-008
title: "Execution Plan: Onboard New ProServ Vendors — Reduce Service Costs"
owner: "claire"
quarter: "2026-Q2"
status: active
created: "2026-04-08"
revised: ""
weeks_remaining: 12
internal_target: "2026-06-16"
hard_deadline: "2026-06-30"
asana_goal_id: "1213964743621568"
asana_project_id: "1213987713544324"
---

# Execution Plan: Onboard New ProServ Vendors — Reduce Service Costs

**Rock:** rock-008 — Onboard New ProServ Vendors (Shipping, Overwrap, Printing, Warehouse)
**Owner:** Claire | **Lead-gen partner:** Francisco | **Due:** Jun 30 (internal target Jun 16) | **Weeks:** 12

## Conceptual Framing

This Rock is **NOT** about platform/engineering integration. The platform's "Get Quote" rate-comparison button is an MVP prototype and is **not used** in this Rock. All quoting in Q2 is **manual** via Google/Excel docs.

This Rock IS about establishing a **manual-quoting partnership** with cheaper ProServ vendors:
1. **Source + RFP + select** new vendors who beat existing partner pricing
2. **List vendors on the Recess platform** so they can receive and accept project offers (existing capability)
3. **Document a manual quoting workflow** that ACs follow until Q3 automates it
4. **Collect API + WMS docs** as raw material for a future Q3 API-integration Rock — we **don't wire any API** in this Rock

The Master Vendor Capability Checklist (Phase IV final deliverable) becomes the operating procedure for the next 3-6 months until Q3 automates it.

## Scope ("Done means...")

| Category | Vendors | API Requirement | Cost Bar | Extra Deliverables |
|---|---|---|---|---|
| Shipping | 3 (hard) | ≥1 with API (hard) | Cheaper than ALL incumbents | Quoting API docs + WMS system named + WMS integration docs |
| Overwrapping | 1 (hard) + 1 stretch | None | Cheaper than incumbent | — |
| 4x6 Printing | 2 | Covered below | Cheaper than incumbent | Rate card + volume tiers + variable-data (QR) pricing + 3rd-party label acceptance |
| Pull-up Banner Printing | 2 | ≥1 of all printing vendors w/ API + placement integration (hard) | Cheaper than incumbent ($150/33" benchmark) | Same as 4x6 |
| Warehouse | 3 | None | Rate card pricing | Unishippers compatibility + decoupling from shipping confirmed |
| **Total finalists** | **11–12 vendors** | **≥4 with API across all categories (3 ship + 1 print)** | All beat incumbent pricing | API/WMS docs feed Q3 Rock |

**Universal RFP question** for shipping + warehouse + printing: *"Can you do your service decoupled from the next step? Can you accept third-party shipping labels (e.g., Unishippers) for fulfillment? Can you generate labels that another fulfillment partner uses?"*

## Capacity Budget

- **Claire:** ~25 hours over 10 weeks (2-3 hrs/week, front-loaded)
- **Francisco:** ~12 hours front-loaded over Weeks 1-2 for lead-gen + relief-valve availability after
- **Char:** ~30 min in Week 2 for HubSpot sequence review + Team Finalist Review Call (May 27, 60 min)
- **Deuce:** Team Finalist Review Call (May 27) + Q3 Handoff Meeting (Jun 16)

## Critical Path

T0.1 (Reference Spec) → T0.5 (RFP templates) → T2.3 (Printing sequence) → T2.4a (Char review) → T2.5 (Launch) → T2.8 (Final cutoff) → T3.3 (Vet printing) → T3.4a (Team Review Call) → T3.7 (Finalize printing) → T4.1 (Platform listing) → T4.4 (Master Checklist) → T4.6 (Team training) → T4.9 (Q3 handoff)

The printing track is the critical path because it has the most acceptance criteria + the hard API requirement + feeds activation.

## Weekly Project Updates

| Task | Owner | Due |
|------|-------|-----|
| Project Status Update – 2026-04-10 | Claire | Apr 10 |
| Project Status Update – 2026-04-17 | Claire | Apr 17 |
| Project Status Update – 2026-04-24 | Claire | Apr 24 |
| Project Status Update – 2026-05-01 | Claire | May 1 |
| Project Status Update – 2026-05-08 | Claire | May 8 |
| Project Status Update – 2026-05-15 | Claire | May 15 |
| Project Status Update – 2026-05-22 | Claire | May 22 |
| Project Status Update – 2026-05-29 | Claire | May 29 |
| Project Status Update – 2026-06-05 | Claire | Jun 5 |
| Project Status Update – 2026-06-12 | Claire | Jun 12 |

## Phase 0 — Setup & Governance (Apr 8-14)

**Outcome:** Project infrastructure ready — Reference Shipment Spec built, RFP templates drafted, Platform Workflow Agreement doc written, Master Google Sheet tracker created, Francisco briefed.

| ID | Task | Owner | Due | Depends On | Milestone |
|---|---|---|---|---|---|
| **MILESTONE: Phase 0 — Project infrastructure ready** | Claire | Apr 14 | — | ✓ |
| T0.1 | Build Reference Shipment Spec v1 (Google/Excel doc — origin warehouse, 5-10 destinations, SKU mix, packaging assumptions) | Claire | Apr 11 | — | Phase 0 |
| T0.2 | Draft Platform Workflow Agreement doc (1-page "what you're agreeing to": offer acceptance via platform, manual quoting via Google/Excel doc, 48-hr turnaround, invoicing process, Q3 API discussion willingness) | Claire | Apr 12 | — | Phase 0 |
| T0.3 | Create Master Google Sheet tracker (columns: category, vendor, source, contact, sequence enrolled y/n, response y/n, response date, quote vs baseline, API y/n, WMS, status) | Claire | Apr 10 | — | Phase 0 |
| T0.4 | Francisco kickoff call — brief on lead-gen sources (HubSpot CRM + 3rd-party network + AI research + referrals), category targets, timeline | Claire + Francisco | Apr 9 | T0.3 | Phase 0 |
| T0.5 | Draft 4 RFP templates (Shipping, Overwrap, Printing, Warehouse) — each with category-specific question set baked in | Claire | Apr 12 | T0.1 | Phase 0 |

## Phase I — Baseline & Candidate Pipeline Ready (Apr 8-21)

**Outcome:** Cost baseline received from incumbents + 60+ candidates sourced into Master Google Sheet across all 5 categories.

| ID | Task | Owner | Due | Depends On | Milestone |
|---|---|---|---|---|---|
| **MILESTONE: Phase I — Baseline & Candidate Pipeline Ready** | Claire | Apr 21 | — | ✓ |
| T1.1 | Pull existing HubSpot CRM ProSVC contacts → Master Google Sheet AND enroll in draft HubSpot sequences | Francisco | Apr 14 | T0.3, T0.4 | Phase I |
| T1.2 | Send Reference Shipment Spec to all incumbent vendors (shipping, overwrap, 4x6 printing, pull-up printing) for baseline re-quote | Claire | Apr 15 | T0.1 | Phase I |
| T1.3 | Source 60 new candidates into Master Google Sheet across 4 categories (24 shipping / 15 printing / 6 overwrap / 15 warehouse) — flag warehouse↔shipping overlaps | Francisco | Apr 21 | T0.3, T0.4 | Phase I |
| T1.4 | Collect incumbent baseline quotes + document in tracker | Claire | Apr 21 | T1.2 | Phase I |
| T1.5 | Publish baseline benchmark doc (per-category incumbent pricing — this is the "cheaper than" bar for the rest of the Rock) | Claire | Apr 21 | T1.4 | Phase I |

## Phase II — RFPs Sent & Responses Collected (Apr 15 - May 12)

**Outcome:** All 4 HubSpot sequences live with all candidates enrolled, Char-approved tone, all responses received or marked dropped, qualified candidates tagged for Phase III.

| ID | Task | Owner | Due | Depends On | Milestone |
|---|---|---|---|---|---|
| **MILESTONE: Phase II — RFPs Sent & Responses Collected** | Claire | May 12 | — | ✓ |
| T2.1 | Build HubSpot 4-step RFP sequence — Shipping (intro + spec attached → follow-up → chaser → last call) | Claire | Apr 22 | T0.5 | Phase II |
| T2.2 | Build HubSpot 4-step RFP sequence — Overwrapping | Claire | Apr 22 | T0.5 | Phase II |
| T2.3 | Build HubSpot 4-step RFP sequence — Printing (with all printing Qs: 3rd-party label acceptance, rate card + 33" benchmark, volume discount at 100 units, variable-data QR pricing) | Claire | Apr 22 | T0.5 | Phase II |
| T2.4 | Build HubSpot 4-step RFP sequence — Warehouse (with Unishippers + decoupling Qs) | Claire | Apr 22 | T0.5 | Phase II |
| T2.4a | **Char reviews all 4 HubSpot sequences** for tone, content, brand voice — approves or requests edits | Char | Apr 23 | T2.1, T2.2, T2.3, T2.4 | Phase II |
| T2.5 | Enroll all candidates in their category HubSpot sequence + launch | Claire | Apr 24 | T1.1, T1.3, T2.4a | Phase II |
| T2.6 | Phase II Kickoff Call (Claire + Francisco) — confirm sequences live, baseline response expectations | Claire + Francisco | Apr 25 | T2.5 | Phase II |
| T2.7 | Status Check Call #1 (Claire + Francisco) — review response rates, decide if top-of-funnel expansion needed | Claire + Francisco | May 5 | T2.6 | Phase II |
| T2.8 | Status Check Call #2 (Claire + Francisco) — final cutoff review, drop non-responders, tag qualified candidates for Phase III | Claire + Francisco | May 12 | T2.7 | Phase II |

**Escalation rule:** If at T2.7 any category has <30% response rate, Francisco immediately sources 10 more candidates for that category (logged as "wave 2" in tracker). Sequence re-enrollment same day by Claire.

## Phase III — Vetting, Team Review & Finalists (May 6 - Jun 2)

**Outcome:** All categories vetted, team finalist review call held, finalists selected and platform workflow agreed, API + WMS docs collected for Q3 handoff.

| ID | Task | Owner | Due | Depends On | Milestone |
|---|---|---|---|---|---|
| **MILESTONE: Phase III — Finalists Selected & Platform Workflow Agreed** | Claire | Jun 2 | — | ✓ |
| T3.1 | Vet Shipping candidates — quote vs baseline, API docs collected, WMS system named, WMS integration docs collected, decoupling Qs answered, Platform Workflow Agreement walked through | Claire | May 26 | T2.8, T1.5, T0.2 | Phase III |
| T3.2 | Vet Overwrap candidates — quote vs baseline, Platform Workflow Agreement walked through | Claire | May 26 | T2.8, T1.5, T0.2 | Phase III |
| T3.3 | Vet Printing candidates — rate card with volume tiers, variable-data (QR) pricing confirmed, 3rd-party label acceptance confirmed, API status (if applicable), Platform Workflow Agreement walked through | Claire | May 26 | T2.8, T1.5, T0.2 | Phase III |
| T3.4 | Vet Warehouse candidates — rate card, Unishippers compatibility, decoupling confirmed, Platform Workflow Agreement walked through | Claire | May 26 | T2.8, T1.5, T0.2 | Phase III |
| T3.4a | **Team Finalist Review Call** (Claire + Francisco + Char + Deuce) — walk through all vetted candidates by category, make final selection decisions together | Claire + Francisco + Char + Deuce | May 27 | T3.1, T3.2, T3.3, T3.4 | Phase III |
| T3.5 | Finalize Shipping Vendors (3 slots, ≥1 API hard) — document selections in tracker + notify winners/losers | Claire | May 28 | T3.4a | Phase III |
| T3.6 | Finalize Overwrap Vendors (1 required + 1 stretch) — document + notify | Claire | May 28 | T3.4a | Phase III |
| T3.7 | Finalize Printing Vendors (4 slots: 2× 4x6, 2× pull-up; ≥1 with API + placement integration hard) — document + notify | Claire | May 28 | T3.4a | Phase III |
| T3.8 | Finalize Warehouse Vendors (3 slots) — document + notify | Claire | Jun 2 | T3.4a | Phase III |
| T3.9 | Collect API quoting docs from shipping API vendors → shared folder (Q3 Rock raw material) | Claire | Jun 2 | T3.5 | Phase III |
| T3.10 | Collect WMS system names + integration docs from shipping finalists → shared folder | Claire | Jun 2 | T3.5 | Phase III |
| T3.11 | Collect API + placement integration docs from printing API vendor → shared folder | Claire | Jun 2 | T3.7 | Phase III |

## Phase IV — Activation, Documentation & Handoff (May 27 - Jun 16)

**Outcome:** All finalists listed on platform, Master Vendor Capability Checklist published, manual quoting process documented, team trained live, cost delta calculated, Rock completion + Q3 scoping memos drafted, Q3 handoff meeting held.

| ID | Task | Owner | Due | Depends On | Milestone |
|---|---|---|---|---|---|
| **MILESTONE: Phase IV — Activated, Documented, Handed Off** | Claire | Jun 16 | — | ✓ |
| T4.1 | List all 11-12 finalists on Recess platform (~15-30 min per vendor; tracker checklist) | Claire | Jun 9 | T3.5, T3.6, T3.7, T3.8 | Phase IV |
| T4.2 | Document manual quoting process per category → team wiki / runbook (this is the operating procedure that replaces the prototype "Get Quote" button until Q3) | Claire | Jun 12 | T4.1 | Phase IV |
| T4.3 | Calculate cost reduction % per category (baseline vs new vendor pricing — headline KPI) | Claire | Jun 12 | T4.1, T1.5 | Phase IV |
| T4.4 | Publish Master Vendor Capability Checklist (Google Sheet "end file" — all 11-12 vendors × all capabilities, cost delta, API y/n, WMS, rate card link, contact) | Claire | Jun 12 | T4.1, T4.3, T3.9, T3.10, T3.11 | Phase IV |
| T4.5 | Schedule live team training session (calendar invite, prep deck) | Claire | Jun 12 | — | Phase IV |
| T4.6 | Hold live team training session (Claire presents new vendors + manual quoting workflow to AC/AM team; recorded for async) | Claire | Jun 16 | T4.4, T4.2, T4.5 | Phase IV |
| T4.7 | Draft Rock completion memo (final vendor count, cost delta, lessons learned, links to all deliverables) | Claire | Jun 14 | T4.3, T4.4 | Phase IV |
| T4.8 | Draft Q3 API Integration Rock scoping memo (which vendors are API-ready, what engineering work is required, rough effort, suggested owner) | Claire | Jun 14 | T3.9, T3.10, T3.11 | Phase IV |
| T4.9 | Hold Q3 Rock handoff meeting (Claire + Char + Deuce) — present scoping memo for Q3 quarterly planning | Claire + Char + Deuce | Jun 16 | T4.7, T4.8 | Phase IV |

**Buffer:** Jun 17-30 (2 weeks) reserved for slippage recovery from Phases II-IV. Internal target Jun 16; hard deadline Jun 30.

## Dependencies & Handoffs

| From | To | What | By When |
|------|-----|------|---------|
| Claire | Claire | Reference Shipment Spec (T0.1) → unblocks RFP templates | Apr 11 |
| Claire | Francisco | Tracker structure + sourcing brief (T0.4) | Apr 9 |
| Francisco | Claire | CRM contacts pulled into tracker (T1.1) | Apr 14 |
| Francisco | Claire | 60 new candidates sourced (T1.3) | Apr 21 |
| Claire | Incumbents | Reference Spec for baseline re-quote | Apr 15 |
| Incumbents | Claire | Baseline quotes back | Apr 21 |
| Claire | Char | 4 HubSpot sequences for review | Apr 22 |
| Char | Claire | Sequences approved (or edits) | Apr 23 |
| Claire | Vendors | HubSpot sequences launched | Apr 24 |
| Vendors | Claire | RFP responses (via HubSpot sequence cadence) | May 12 |
| Claire | Team (Francisco, Char, Deuce) | Vetted candidates ready for review | May 26 |
| Team | Claire | Finalist selections | May 27 |
| Claire | Char + Deuce | Q3 Rock scoping memo | Jun 14 |
| Claire | AC/AM team | Live training session + recording | Jun 16 |

## Risks

| # | Risk | Impact | Likelihood | Mitigation |
|---|---|---|---|---|
| R1 | Francisco can't hit 60 candidates in 12 hours | HIGH (blocks Phase II) | MEDIUM | Focus warm sources first (CRM + 3rd-party network); below 40 by Apr 17 → triage to 40-target; T2.7 catches low response rate → Francisco sources wave 2 |
| R2 | Shipping <3 qualifying vendors (no API partner found) | HIGH (fails hard requirement) | MEDIUM | Escalate at T2.7. Deuce decides whether to relax API requirement or extend Phase II by 1 week (eats buffer) |
| R3 | HubSpot sequences flagged as spam by enterprise vendors | MEDIUM | MEDIUM | Char reviews tone (T2.4a); warm Step 1 with personalization, Claire's sender identity, vendor name + project context in opener |
| R4 | Incumbent vendors refuse baseline re-quote | MEDIUM | LOW | Fallback: use last-3-months invoice average from Ines |
| R5 | No printing vendor with API + placement integration in pool | MEDIUM (fails hard requirement) | MEDIUM | At T2.7, audit printing responses for API capability. If zero, Francisco sources 5 more printing candidates targeting API-capable vendors (Vistaprint, 4over, PrintingForLess have APIs) |
| R6 | Claire's capacity eaten by other Q2 AC work | MEDIUM | MEDIUM | Francisco relief-valve activates; he picks up scheduling and initial qualification calls |

## Assumptions

- A1: Francisco has ~12 hours available over Weeks 1-2 for lead-gen, prioritized above most other work
- A2: HubSpot sequences are acceptable RFP delivery (Char approves tone in T2.4a)
- A3: Incumbent vendors will re-quote the Reference Shipment Spec cooperatively
- A4: Claire has unilateral authority to activate new ProSVC vendors on platform without per-vendor legal/MSA review
- A5: Vendor listings and the platform offer-acceptance workflow are production-live. **"Get Quote" rate comparison is MVP/prototype and is NOT relied upon in this Rock — all quoting is manual via Google/Excel docs until Q3 API Rock**
- A6: Claire's 2-3 hrs/week + Francisco's 12 hrs are protected from interruption during front-loaded weeks
- A7: Char and Deuce are available for Team Finalist Review Call (May 27) and Q3 Handoff meeting (Jun 16)
- A8: Char has ~30 min of capacity to review HubSpot sequences on Apr 23

## Tracking

- **Source of truth:** Master Google Sheet tracker (created in T0.3) — evolves from candidate pipeline → response tracker → vetting scorecard → Master Vendor Capability Checklist (end file)
- **Asana:** parent tasks per phase; per-vendor tracking in Google Sheets, not Asana, to keep My Tasks board lean
- **L10 check-in:** Claire reports on/off track weekly via Friday Project Status Update
- **Slip rule:** If a task slips twice, flag as milestone risk in next Weekly Status Update. If a phase milestone slips by 5+ days, escalate to Deuce via L10 IDS

## Notes

- 2026-04-08: Plan created via 5-round facilitation with Deuce. Discovery doc (recess-prd 01_DISCOVERY/professional-services/) provided context; this Rock is a partnership/sourcing Rock, not engineering. API integration deferred to Q3.
- 2026-04-08: Scope locked at 11-12 finalists across 5 categories (3 ship + 1-2 overwrap + 4 printing + 3 warehouse). Hard API minimums: ≥1 shipping + ≥1 printing.
- 2026-04-08: Conceptual correction — "Get Quote" button is MVP prototype, not production. All quoting in Q2 is manual via Google/Excel docs. Phase IV's manual quoting process documentation is therefore the centerpiece operational deliverable.
- 2026-04-08: Char added as HubSpot sequence reviewer (T2.4a) and Team Finalist Review Call attendee (T3.4a) per Deuce direction.
- 2026-04-08: Francisco confirmed at 12 hours capacity for lead-gen front-loaded over Weeks 1-2.
