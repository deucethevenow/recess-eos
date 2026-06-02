---
name: critic-review
description: >
  Multi-model adversarial review with EOS domain expertise. Runs
  learnings-researcher for known patterns, OpenAI for independent review,
  and an EOS-specific critic for orchestration safety checks. Use before
  committing any non-trivial changes.
argument-hint: "[optional: focus area like 'contract' or 'config']"
---

# /critic-review — Multi-Model Adversarial Review

Orchestrates three layers of code review before commit:
1. **Institutional Knowledge** — surfaces relevant past corrections from `.claude/learnings/`
2. **External Adversarial** — OpenAI independent review via `openai-review` script
3. **EOS Domain Critic** — orchestration-specific safety checks (registry, contracts, events)

## Usage

```bash
/critic-review                     # Full review of current changes
/critic-review contract            # Focus on contract/config patterns
/critic-review --skip-external     # Skip OpenAI (save API calls for small changes)
```

## Execution Flow

### Phase 1: Surface Relevant Learnings

Dispatch `learnings-researcher` agent with the current task/feature context.

### Phase 2: External Adversarial Review

**Skip if `--skip-external` was passed or OPENAI_API_KEY is unset.**

```bash
/Users/deucethevenowworkm1/.local/bin/openai-review
```

Graceful degradation: if unavailable, continue with Phase 1 + Phase 3.

### Phase 3: EOS Domain Critic

Dispatch `eos-critic` agent with the git diff and learnings brief. Runs 10 mandatory checks:
1. Registry override detection
2. Silent defaults on contract fields
3. Immutable event violations
4. API escaping errors
5. Type contract (safe_float) violations
6. Sensitivity routing leaks
7. Config goals pointer-only enforcement
8. Snapshot-driven metric compliance
9. NaN safety
10. Fireflies title matching

### Phase 4: Synthesis

Combine findings with severity: [CRITICAL] → [WARNING] → [SUGGESTION].

### Phase 5: Address Findings

Fix all [CRITICAL]. Fix [WARNING] unless strong reason not to. Consider [SUGGESTION].

### Phase 6: Learning Loop Integration

If any fix revealed a new pattern not in `.claude/learnings/`, suggest running `/learn`.

## Prerequisites

**Required:** `.claude/learnings/` with schema.yaml
**Optional:** `OPENAI_API_KEY` for Phase 2 external review

## Related

- `learnings-researcher` agent — surfaces past corrections
- `eos-critic` agent — 10-check domain review
- `/learn` skill — capture new corrections
