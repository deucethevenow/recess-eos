---
id: rock-009
title: "AI Harness Live — <5 Fixes per User Flow PR"
owner: "arbind"
quarter: "2026-Q2"
status: on_track
created: "2026-04-09"
due: "2026-06-30"
annual_goal: "Operational Leverage (Goal #4)"
kpi_target: "90% of AI-generated user flows require <5 manual fixes to merge, measured from BQ Harness Log across Recess-Marketplace and recess-ui"
asana_goal_id: "1213995518121111"
asana_project_id: "1213995392945452"
collaborators:
  - anderson
  - mateus
  - lucas
  - leo
  - deuce
target_repos:
  - Recess-Marketplace
  - recess-ui
milestones:
  - title: "Codebase governance + AI context coverage — .claude/rules shipped in both repos, CODEOWNERS + branch/commit conventions in place, validated with 1 real AI-generated PR per repo"
    due: "2026-05-02"
    status: todo
  - title: "Harness infrastructure — automated PRD→PR→metrics→dashboard loop running: BQ Harness Log table, agent/adapter, coverage reporting, auto PR summary bot, end-to-end verified"
    due: "2026-05-15"
    status: todo
  - title: "Calibration to <5 fix threshold — 2 consecutive weeks of ≥90% of user-flow PRs at ≤5 fixes (BQ-verified), tuning playbook captured"
    due: "2026-06-15"
    status: todo
  - title: "Quality floor enforced + Datadog cleanup — CI hard-fails <90% coverage in both repos, Datadog noise at ≤50% of Apr 13 baseline, sustained 90% fix-count through Jun 30"
    due: "2026-06-30"
    status: todo
tracking:
  type: "self-instrumented + dashboard"
  source: "BQ Harness Log table (App_Recess_OS or dedicated dataset)"
  dashboard: "Leo-built dashboard on Harness Log — rolling 2-week % of user-flow PRs at ≤5 fixes per repo + combined"
  hard_escalation_gate: "2026-05-29 — if data isn't trending toward 90%, Lucas escalates in L10 same week"
  baselines:
    datadog_noise: "Captured 2026-04-13 by Anderson, frozen — 50% reduction target for Phase IV"
    harness_log: "Manual v0 from Apr 10 (Google Sheet), automated from Apr 15 (BQ)"
attachments:
  - path: "data/rocks/2026-Q2/plans/plan-009-ai-harness.md"
    label: "Execution plan (plan-009)"
---

# AI Harness Live — <5 Fixes per User Flow PR

## Why This Is a Company Rock

Every unchecked AI-generated PR today costs reviewer time and masks quality issues. Without codified context, automated measurement, and an enforced quality floor, the team is carrying the cognitive load of re-explaining the same rules on every PR. This Rock turns that implicit work into a system: the AI knows the rules (`.claude/rules`), the PR process captures the fix count (PRD template + adapter), the dashboard shows the trend (BQ Harness Log), and CI enforces the floor (hard-fail <90% coverage). Supports Goal #4 — Operational Leverage.

## Measurable Outcome

**90% of AI-generated user flows require <5 manual fixes to merge**, measured by:

1. Every subdirectory (1 per repo across 2 codebases: Recess-Marketplace, recess-ui) has `.claude/rules` shipped, reviewed, and validated by a real AI-generated PR.
2. Automated PR summaries posting on every new PR in both repos.
3. Git commit history shows <5 fix-commits per user-flow PR, measured from the BQ Harness Log over a rolling 2-week window (≥90% of PRs).
4. CI hard-fails any PR where coverage drops below 90% in both repos.
5. Datadog noise reduced by 50% from the Apr 13 frozen baseline.

**"Done" is binary:** either all 5 criteria are true on Jun 30 or the Rock is dropped and reconstituted.

## Milestones

- [ ] **Codebase governance + AI context coverage** — May 2 *(extended from Apr 30 per plan-009 Option B slip)*
- [ ] **Harness infrastructure (automated PRD flow)** — May 15
- [ ] **Calibration to <5 fix threshold** — Jun 15
- [ ] **Quality floor enforced + Datadog cleanup** — Jun 30

## Dependencies

- **PRD template ("Structured User Flow Stats")** already in use in both repos — this is the input format for AI generation and the source of user-flow definitions. Pre-existing; not a Rock deliverable.
- **BQ destination** — Harness Log table lives in BigQuery (not Datadog). Leo builds + configures (Apr 14); Arbind's adapter writes to it (Apr 15).
- **Arbind as Rock owner** coordinates across 6 people: Anderson (Datadog), Mateus (AI context), Lucas (calibration), Leo (dashboard), Deuce (weekly review as EOS project).

## Tracking

- **KPI source:** Self-instrumented. Harness Log begins as a Google Sheet (Apr 10) and migrates to BQ (Apr 15). No pre-existing dashboard to reuse.
- **Dashboard:** Leo-built, live by Apr 17 — rolling 2-week % of user-flow PRs at ≤5 fixes per repo + combined, coverage trend, Datadog noise trend.
- **Weekly review:** Deuce runs as an EOS project (outside this Rock's task list). Findings feed Lucas's failure-mode analysis.
- **L10 check-in:** Arbind reports on/off track weekly.
- **Hard escalation gate:** May 29 — if data isn't trending toward 90%, Lucas escalates in L10 same week (before Phase IV enforcement can ship).

## Execution Plan

Detailed weekly tasks, dependencies, handoffs, and risks are in `data/rocks/2026-Q2/plans/plan-009-ai-harness.md` (created 2026-04-08 via `ceos-rock-plans`, 5-round facilitated).

## Notes
- 2026-04-08: Plan-009 created via `ceos-rock-plans` (originally plan-008; renamed 2026-04-09 alongside Rock ID swap)
- 2026-04-09: Rock created via `ceos-rocks`. Phase I milestone reflects Option B slip (May 2, was Apr 30).
