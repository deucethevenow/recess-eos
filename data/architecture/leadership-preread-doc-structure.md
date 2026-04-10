# Leadership Pre-Read Doc Structure

> Reference: Google Doc `1DGHFBjXsfb1kb438QRPH9QZlG9fE2CzBs1WPtDP0AAU`
> Last verified: 2026-04-10 (April 9th tab)

## Document Layout

The doc uses **tabs** — one per meeting date plus a reusable template tab.
Each tab is a complete pre-read for that meeting.

### Tabs (as of Apr 10)

| Tab | Content |
|-----|---------|
| April 9th 2026 | Most recent meeting pre-read |
| March 26th 2026 | Prior meeting |
| March 12th 2026 | Older meeting |
| Agenda template | Reusable blank template |

### New meeting flow

Copy the "Agenda template" tab, rename to the meeting date, and populate.

## Sections (in order, per tab)

### 1. Header

- Title: `RECESS- [DATE]`
- Subtitle: `Leadership Team Pre-Read Memo`
- How-it-works blurb: "Each leader completes their section and submits 24 hours before the meeting. Everyone reads all sections before arriving."

### 2. Meeting Prep Checklist (table)

| # | Owner | Task | Deadline |
|---|-------|------|----------|
| 1 | Jack & Deuce | Fill in Founder's Agenda: strategic context, discussion topics, pending decisions | 4 days before meeting |
| 2 | Dept Leads | Fill in full section: scorecard, in progress, next & blockers, wins/worries/wants, decisions, FYIs | 3 days before meeting |
| 3 | Ines | Pull last meeting's action items, mark carryovers, add Last Meeting Recap | 3 days before |
| 4 | (implied) | Review all sections | 1 day before |
| 5 | (implied) | Prepare questions / discussion points | 1 day before |
| 6 | Facilitator | Build meeting agenda from submitted memos (yellow/red metrics, decisions, wants) | Night before / morning of |

> **Phase 2 automation targets:** Row 3 (Ines's job) is replaced by `ceos-leadership-prep` Round 1 + action item extraction. Row 6 (facilitator agenda) is partially automated by Round 4.

### 3. Action Items (from last meeting)

Structured list with:
- **Category header** (e.g., "Sales & Strategy", "Sales Operations", "Measurement & Pricing", "Team Meeting Agenda", "Sales Messaging", "Other")
- Per item:
  - Action item description
  - `Responsible:` owner name(s)
  - `Deadline:` date or "Not specified"
  - `Details:` (optional) additional context

> **Phase 2 insertion point:** `action_item_extractor.py` populates this from Fireflies transcript. `action_item_matcher.py` cross-references against Asana To-Dos for status.

### 4. Last Meeting Recap

- **Key Takeaways:** bullet list of 3-5 major outcomes
- **Call Notes:** longer-form grouped by topic (e.g., "Q2 Engineering Priorities", "Pricing and Product Updates", "Back to College Program Timing", "Culture Interview Process", "Dashboard and Reporting Infrastructure")

> **Phase 2 insertion point:** Round 1 auto-generates this from Fireflies transcript summary.

### 5. Meeting Agenda (table)

Header: `MEETING AGENDA — Built by the facilitator after all memos are submitted`

| Time | Topic | Lead | Notes |
|------|-------|------|-------|

Includes standing items like "Rotate the facilitator. Each meeting a different leader runs it. Founders participate, not dominate."

### 6. Founder's Agenda

Header: `FOUNDER'S AGENDA — Completed by: Jack (CEO) & Deuce (COO) • Due: 4 days before meeting`

Free-form strategic content. Recent example topics:
- Culture interview process updates
- Decisions needing leadership input

> **Phase 2 insertion point:** Rounds 2-4 capture this interactively from Jack + Deuce.

### 7. Company-Wide Updates

Header: `COMPANY-WIDE UPDATES — Announcements affecting multiple teams`

Brief bullets affecting the whole org.

### 8-13. Department Sections (one per dept lead)

Each department follows an identical structure:

**Header format:** `[DEPT] UPDATE — Completed by: [Role] ([Name]) • Due: 3 days before meeting`

**Subsections:**
1. **SCORECARD** — table with key metrics (last 2 weeks for bi-weekly cadence)
2. **In Progress** — current work items
3. **Next & Blockers** — upcoming work + anything blocked
4. **Wins / Worries / Wants** — freeform
5. **Decisions Needed** — items requiring leadership input
6. **FYIs** — Hiring updates, escalations, process changes, PTO

**Department order (as of April 9th):**

| # | Header | Owner |
|---|--------|-------|
| 8 | OPERATIONS UPDATE | COO (Deuce) |
| 9 | ENGINEERING UPDATE | Head of Engineering (Arbind) |
| 10 | SALES UPDATE | Head of Sales (Danny) |
| 11 | ACCOUNT MANAGEMENT UPDATE | Head of AM (Char) |
| 12 | BIZ DEV UPDATE | CEO (Jack) |

> **Note:** Marketing (Courtney), Supply (Ian), and AI Automations (Leo) do not have sections in the April 9th tab. They may be added in future meetings or report through other channels.

## Insertion Points for ceos-leadership-prep

| Round | Doc Section | Action |
|-------|------------|--------|
| Round 1 (Context Pull) | §3 Action Items + §4 Last Meeting Recap | Auto-populate from Fireflies + Asana |
| Round 2 (Top of Mind) | — | Capture only (not written to doc yet) |
| Round 3 (Decisions) | — | Capture only |
| Round 4 (Discussion Topics) | §6 Founder's Agenda | Write strategic topics |
| Round 5 (Write to Doc) | All above + §5 Meeting Agenda | Final write + Asana tasks + Slack |

## Insertion Points for leadership-preread (existing skill)

The existing `leadership-preread` skill populates SCORECARD tables in each department section (§8-13). It queries BigQuery for the latest metric values and writes them into the scorecard table cells.

## Google Doc API Notes

- Tabs are accessed via `tabId` in the Google Docs API
- New meeting = copy "Agenda template" tab, rename
- Text insertion uses character indices (shown in the raw doc content as `[start-end]` ranges)
- Tables are structured elements — scorecard updates target specific table cells
