---
id: plan-009
rock_id: rock-009
title: "Execution Plan: AI Harness Live — <5 Fixes per User Flow"
owner: "arbind"
quarter: "2026-Q2"
status: active
created: "2026-04-08"
revised: "2026-04-09"
weeks_remaining: 12
asana_goal_id: "1213995518121111"
asana_project_id: "1213995392945452"
---

# Execution Plan: AI Harness Live — <5 Fixes per User Flow

**Rock:** rock-009 — AI Harness Live, <5 Fixes per User Flow PR
**Owner:** Arbind | **Due:** Jun 30 | **Weeks:** 12
**Supports:** Goal #4 — Operational Leverage
**KPI:** 90% of AI-generated user flows require <5 manual fixes to merge
**Collaborators:** Anderson, Mateus, Lucas, Leo, Deuce
**Target repos:** Recess-Marketplace, recess-ui

## Architecture Summary

Two workstreams running in parallel, converging into a single measurement-and-enforcement loop:

| Layer | What | Who |
|---|---|---|
| **Measurement stack** (Phase 0) | BQ Harness Log table, agent/skill/adapter pushing PR + commit + coverage metrics, dashboard | Arbind + Leo |
| **AI context** (Phase I-A) | `.claude/rules` in both repos codifying banned/required patterns, gotchas, deploy rules | Mateus (w/ Lucas audit support) |
| **Governance** (Phase I-B) | CODEOWNERS, branch/commit conventions, shipped governance artifacts | Arbind |
| **PR automation** (Phase II) | Auto PR summary bot, adapter hardening, full end-to-end verification | Arbind |
| **Calibration** (Phase III) | Failure-mode analysis, rules tuning, playbook | Lucas + Mateus |
| **Enforcement** (Phase IV) | CI hard-fail <90% coverage; Datadog 50% noise reduction | Arbind (CI) + Anderson (Datadog) |

**Key decision: PRD template is the source of user-flow definitions.** There is no separate PR template. The existing "Structured User Flow Stats" PRD template already declares user flows; the Harness Log counts fix-commits per declared flow.

**Key decision: Metrics flow to BigQuery, not Datadog.** Arbind's adapter writes to a BQ Harness Log table; Leo builds the dashboard on top. Anderson's Datadog cleanup runs as a fully independent parallel track.

## Sequencing Decisions

1. **Measurement stack lives in Phase 0, not Phase II** — pulled forward from May 15 to Apr 17 so calibration data collection starts 4 weeks earlier. This roughly doubles the calibration window (from ~4 weeks to ~8 weeks of real data) and dramatically increases the chance of catching "threshold not achievable" early enough to course-correct.
2. **PRD template already exists** — removed from Phase I as a completed prerequisite.
3. **Lucas audits recess-ui in Phase I** — gives him early codebase exposure before his Phase III calibration role. He understands *why* PRs fail, not just counts them.
4. **Phase I ship date extended to May 2** (was Apr 30) — Option B slip absorbs one-day review→ship→validate collision without compromising validation quality. Phase II tasks don't start until May 5, so the slack absorbs the slip.
5. **Deuce runs weekly data review as an EOS project**, outside this Rock's task list — the review cadence is a recurring EOS workstream, not a Rock deliverable.
6. **Datadog cleanup runs fully parallel** — no shared namespace with the harness (metrics go to BQ), so Anderson has independent runway from Week 1 through Jun 28.

## Weekly Project Updates

| Task | Owner | Due |
|------|-------|-----|
| Project Status Update – 2026-04-11 | Arbind | Apr 11 |
| Project Status Update – 2026-04-18 | Arbind | Apr 18 |
| Project Status Update – 2026-04-25 | Arbind | Apr 25 |
| Project Status Update – 2026-05-02 | Arbind | May 2 |
| Project Status Update – 2026-05-09 | Arbind | May 9 |
| Project Status Update – 2026-05-16 | Arbind | May 16 |
| Project Status Update – 2026-05-23 | Arbind | May 23 |
| Project Status Update – 2026-05-30 | Arbind | May 30 |
| Project Status Update – 2026-06-06 | Arbind | Jun 6 |
| Project Status Update – 2026-06-13 | Arbind | Jun 13 |
| Project Status Update – 2026-06-20 | Arbind | Jun 20 |
| Project Status Update – 2026-06-26 | Arbind | Jun 26 |

## Weekly Plan

### Week 1 (Apr 8–12) — Definitions, Schema, Baselines

| Task | Owner | Due | Depends On | Milestone |
|------|-------|-----|------------|-----------|
| 0.1 Define user flow + fix + KPI metrics definitions doc (spec for Leo's dashboard) | Arbind | Apr 10 | — | Phase 0 |
| 0.2 Manual Harness Log v0 (Google Sheet) | Arbind | Apr 10 | 0.1 | Phase 0 |
| 0.5 Draft BQ Harness Log schema spec | Arbind | Apr 11 | 0.1 | Phase 0 |
| I-A.1 Audit Recess-Marketplace — banned/required patterns, gotchas | Mateus | Apr 15 | — | Phase I |
| I-A.2 Audit recess-ui — same | Lucas | Apr 15 | — | Phase I |

### Week 2 (Apr 13–19) — Measurement Stack Live + AI Context Audit

| Task | Owner | Due | Depends On | Milestone |
|------|-------|-----|------------|-----------|
| 0.3 Backfill 2 historical PRs into Manual Log | Arbind | Apr 13 | 0.1, 0.2 | Phase 0 |
| 0.4 Capture Datadog noise baseline (frozen number + methodology) | Anderson | Apr 13 | — | Phase IV |
| 0.6 Build + configure BQ Harness Log table | Leo (Arbind schema support) | Apr 14 | 0.5 | Phase 0 |
| 0.7 Build agent + skill + adapter to push PR/commit/coverage → BQ | Arbind | Apr 15 | 0.6 | Phase 0 |
| I-B.1 Draft CODEOWNERS for both repos | Arbind | Apr 17 | — | Phase I |
| 0.8 Build dashboard + verify metrics flowing end-to-end (incl coverage) | Leo | Apr 17 | 0.7 | Phase 0 |
| **MILESTONE 0: Measurement stack operational, data flowing to BQ, dashboard live** | Arbind | Apr 17 | 0.8 | ✓ |

### Weeks 3–4 (Apr 20 – May 2) — AI Context + Governance Shipped

| Task | Owner | Due | Depends On | Milestone |
|------|-------|-----|------------|-----------|
| I-B.3 Document branch/commit conventions (so adapter parses history reliably) | Arbind | Apr 20 | — | Phase I |
| IV.4 Audit current Datadog alerts — actionable / noise / dead | Anderson | Apr 24 | 0.4 | Phase IV |
| I-A.3 Draft `.claude/rules` for Recess-Marketplace | Mateus | Apr 28 | I-A.1 | Phase I |
| I-A.4 Draft `.claude/rules` for recess-ui | Mateus | Apr 28 | I-A.2 | Phase I |
| I-A.5 Review both drafts with Arbind | Mateus + Arbind | Apr 28 | I-A.3, I-A.4 | Phase I |
| I-B.4 Ship governance artifacts (CODEOWNERS, conventions) | Arbind | Apr 28 | I-B.1, I-B.3 | Phase I |
| I-A.6 Ship `.claude/rules` to both repos | Mateus | Apr 29 | I-A.5 | Phase I |
| I-C.1 Validation PR per repo — verify rules loaded, no banned-pattern violations, metrics flowing to BQ | Mateus + Arbind | May 1 | I-A.6, I-B.4 | Phase I |
| **MILESTONE 1: AI context + governance shipped + validated** | Arbind | May 2 | I-C.1 | ✓ |

### Weeks 5–6 (May 3 – May 16) — Harness Infrastructure Polish

| Task | Owner | Due | Depends On | Milestone |
|------|-------|-----|------------|-----------|
| IV.5 Datadog first cleanup pass — delete/silence dead alerts | Anderson | May 8 | IV.4 | Phase IV |
| II.1 GitHub Action: auto PR summary bot (comment on every new PR) | Arbind | May 5 | 0.7, I-B.4 | Phase II |
| II.2 Harden Phase 0 adapter — error handling, retries, gap detection | Arbind | May 12 | 0.7 | Phase II |
| II.3 End-to-end verification: real PR → summary + coverage + BQ row + dashboard update | Arbind | May 14 | II.1, II.2 | Phase II |
| **MILESTONE 2: Full automated PRD→PR→metrics→dashboard loop running in both repos** | Arbind | May 15 | II.3 | ✓ |

### Weeks 7–10 (May 17 – Jun 13) — Calibration

| Task | Owner | Due | Depends On | Milestone |
|------|-------|-----|------------|-----------|
| III.1 Categorize every >5-fix PR by failure mode (missing context, novel framework, human-introduced, banned-pattern slip) | Lucas | ongoing (May 18 → Jun 12) | II.3 | Phase III |
| III.2 Escalate failure patterns to Mateus (rules) and/or Arbind (infra) | Lucas | ongoing | III.1 | Phase III |
| III.3 Tuning round 1 — Mateus updates `.claude/rules` based on findings | Mateus | May 29 | III.2 | Phase III |
| IV.6 Datadog tune alert thresholds for noisy-but-actionable alerts | Anderson | May 29 | IV.5 | Phase IV |
| **HARD ESCALATION GATE: If data isn't trending toward 90% by May 29, Lucas escalates in L10** | Lucas | May 29 | III.1 | — |
| III.4 Tuning round 2 — second pass after 2 more weeks of data | Mateus | Jun 8 | III.3 | Phase III |
| III.5 Capture tuning playbook doc (inputs for Phase IV) | Lucas | Jun 12 | III.4 | Phase III |
| IV.7 Datadog second cleanup pass — interim noise reduction measurement | Anderson | Jun 12 | IV.6 | Phase IV |

### Weeks 11–12 (Jun 14 – Jun 30) — Enforcement & Closeout

| Task | Owner | Due | Depends On | Milestone |
|------|-------|-----|------------|-----------|
| **MILESTONE 3: 2 consecutive weeks of ≥90% of user-flow PRs at ≤5 fixes (BQ-verified)** | Lucas | Jun 15 | III.4, III.5 | ✓ |
| IV.1 Configure CI hard-fail <90% coverage in Recess-Marketplace | Arbind | Jun 22 | Milestone 3 | Phase IV |
| IV.2 Configure CI hard-fail <90% coverage in recess-ui | Arbind | Jun 22 | Milestone 3 | Phase IV |
| IV.3 Test the gate — push intentional low-coverage PR, confirm block | Arbind | Jun 24 | IV.1, IV.2 | Phase IV |
| IV.8 Final Datadog measurement vs baseline; confirm ≤50% | Anderson | Jun 28 | IV.7 | Phase IV |
| IV.9 Lucas confirms Harness Log shows sustained 90%+ in 2 weeks pre-Jun 30 (no regression after CI hard-fail) | Lucas | Jun 28 | IV.3 | Phase IV |
| **MILESTONE 4: CI enforcement live + Datadog ≤50% noise + sustained 90% fix-count** | Arbind | Jun 30 | IV.3, IV.8, IV.9 | ✓ |

## Dependencies & Handoffs

| From | To | What | By When |
|------|-----|------|---------|
| Arbind | All 6 | User flow + fix + KPI metrics definitions doc | Apr 10 |
| Arbind | Leo | BQ schema spec (for table build) | Apr 11 |
| Leo | Arbind | BQ Harness Log table live (for adapter build) | Apr 14 |
| Arbind | Leo | Adapter writing to BQ (for dashboard verify) | Apr 15 |
| Leo | Lucas + Deuce | Dashboard live (data ready for review) | Apr 17 |
| Mateus + Arbind | Phase II | Phase I shipped — stable rules + governance for infra to build against | May 2 |
| Arbind | Lucas | Phase II stable — calibration data ready | May 15 |
| Lucas | Mateus | Failure-mode reports → triggers rules tuning | recurring, weekly |
| Lucas | Arbind | "Threshold provably hit" signal → green light for CI hard-fail | Jun 15 |
| Anderson | Arbind | Datadog cleanup status (independent but in weekly update) | recurring |
| Deuce | All | Weekly BQ data review (EOS project, outside Rock task list) | recurring from Apr 20 |

## Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| 0.6 BQ table slips past Apr 14 | Arbind's adapter blocked → dashboard empty → cascades to Phase 0 miss | Arbind + Leo sync on Apr 11 to lock schema handoff; Leo blocks Apr 12–14 for build |
| 0.7 adapter slips past Apr 15 | Dashboard shows nothing on Apr 17 → Phase 0 miss → Phase III data window shrinks | Arbind clears calendar Apr 14–15; no competing commitments |
| I-A.5 review surfaces major rewrites | Apr 28 → Apr 29 ship is one-day turnaround; rewrites push past milestone | Arbind reviews Mateus's drafts in-progress (not just at Apr 28); catch issues early |
| Low PR volume during calibration | <90% threshold untestable — no statistical power | Monitor weekly PR count from Apr 17. If <5 user-flow PRs/week combined, escalate in L10 |
| Threshold not achievable | Phase III misses → Phase IV CI hard-fail can't ship | **Hard gate May 29**: data must trend toward 90% or Lucas escalates |
| Turning on CI hard-fail too early | Breaks every PR, team disables it | Phase IV gate (IV.3 intentional block test) only runs *after* Phase III proves the bar is reachable |
| Mateus bandwidth split with BAU | I-A.3/I-A.4 drafts slip → Phase I ships late | Confirmed full-time assumption; escalate immediately if BAU intrudes |

## Assumptions

- Arbind has ~70%+ capacity through mid-April for the Phase 0 plumbing sprint (5 deliverables in 7 days)
- Leo can commit Apr 12–14 for BQ table build once Arbind hands off the schema spec
- Mateus is full-time or near-full-time on Phase I AI context work Apr 8 → Apr 29
- Lucas has capacity for ongoing failure-mode analysis May 18 → Jun 12 (~1 day/week)
- Both Recess-Marketplace and recess-ui have ≥5 user-flow PRs/week combined — enough volume to produce meaningful calibration data
- PRD template ("Structured User Flow Stats") is already in use in both repos on Day 1
- Anderson's Datadog cleanup is fully independent of harness work (confirmed — metrics go to BQ)
- Both repos have CI systems that can be configured to hard-fail on coverage (no greenfield CI setup needed)
- Coverage tool exists or can be chosen quickly in each repo
- Deuce's EOS weekly review cadence starts the week of Apr 20, once Phase 0 dashboards go live

## Tracking

- **Dashboard:** Leo-built BQ dashboard on Harness Log table — rolling 2-week % of user-flow PRs at ≤5 fixes per repo + combined; coverage trend per repo; Datadog noise trend
- **Manual:** Datadog cleanup progress (Anderson updates in weekly status); Phase I audit progress (Mateus + Lucas)
- **L10 check-in:** Arbind reports Rock on/off track weekly; plan progress reviewed via Weekly Project Updates
- **Weekly data review:** Deuce runs separately as an EOS project — findings feed Lucas's failure-mode analysis
- **Hard escalation gate:** May 29 — if data isn't trending to 90%, Lucas escalates in L10 same week
- **Slip rule:** If a task slips twice, flag as milestone risk in next Weekly Status Update

## Notes
- 2026-04-08: Plan created via `ceos-rock-plans` — 5-round facilitated build
- Rock file `rock-009-ai-harness.md` created via `/ceos-rocks` (ID reassigned from 008 → 009 on 2026-04-09 to resolve collision with ProServ Vendors Rock)
