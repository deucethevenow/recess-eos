---
name: learn
description: >
  Capture a correction to agent-generated code as a structured learning in
  .claude/learnings/. Coordinates parallel subagents to analyze context, extract
  the solution, find related docs, develop prevention, and classify the entry.
  Adapted for the Recess OS (EOS) Python orchestration domain.
argument-hint: "[optional: brief context about the fix]"
---

# /learn — Capture Corrections (Parallel Subagent Mode)

Coordinate multiple subagents working in parallel to document a recently solved correction from the EOS project. Creates structured documentation in `.claude/learnings/` with schema-validated YAML frontmatter.

## Purpose

Captures corrections to agent-generated Python/SQL/config code while context is fresh. Each documented correction compounds the project's institutional knowledge: the next time Claude hits the same pattern, `learnings-researcher` surfaces the past correction before the agent writes bad code again.

## Usage

```bash
/learn                    # Capture the most recent correction
/learn [brief context]    # Provide additional context hint
/learn --compact          # Compact-safe mode (single pass, no subagents)
```

## Execution Strategy

**Always run full mode by default.** Proceed directly to Phase 0 unless explicitly told to use compact mode.

---

## Full Mode

<critical_requirement>
**Only ONE file gets written — the final learning entry.**
Phase 1 subagents return TEXT DATA only. Only the orchestrator (Phase 2) writes the final file.
</critical_requirement>

### Phase 0: Verify Working Directory

Confirm `.claude/learnings/schema.yaml` exists. If not found, return error.

### Phase 1: Parallel Research (5 subagents)

1. **Context Analyzer** — Extract module, symptoms, affected_files from conversation/diff
2. **Solution Extractor** — What went wrong, why (EOS-specific reasoning), correct pattern
3. **Related Docs Finder** — Grep `.claude/learnings/` for duplicates and cross-references
4. **Prevention Strategist** — How to avoid next time, what test/guard would catch it
5. **Category Classifier** — Classify problem_type, component, root_cause, severity, tags

**Directory mapping:**
- `config_logic_duplication`, `contract_validation_error`, `silent_default_corruption` → `config-contract-issues/`
- `api_escaping_error`, `external_match_failure` → `api-integration-issues/`
- `immutable_event_violation`, `payload_build_error`, `nan_safety_violation` → `data-layer-issues/`
- `type_contract_violation` → `type-safety-issues/`
- `deployment_misconfiguration` → `deployment-issues/`
- All others → `config-contract-issues/` (default)

### Phase 2: Assembly & Write

Assemble file with validated YAML frontmatter + sections: What the agent does wrong, Why it's wrong, Correct pattern, Prevention. Write ONE file. Do NOT auto-commit.

### Phase 2.5: Elevation Check

If same `root_cause` + `component` captured 3+ times → prompt to promote to `critical-patterns.md`.

---

## Compact-Safe Mode (/learn --compact)

Single-pass: extract, classify, check duplicates, write minimal entry. Skip elevation.

---

## Auto-Invoke Triggers

- "the agent got that wrong"
- "config override again"
- "contract error"
- "Claude missed this"
- "had to fix the escaping"

## Related

- `learnings-researcher` agent — surfaces relevant past learnings
- `eos-critic` agent — 10-check domain-specific review
- `.claude/learnings/schema.yaml` — enum validation source of truth
- `.claude/learnings/patterns/critical-patterns.md` — elevated patterns (max 10)
- `context/LEARNINGS.md` — legacy gotcha log (monolithic). New corrections go to `.claude/learnings/`
