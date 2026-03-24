---
id: {{id}}
rock_id: {{rock_id}}
title: "{{title}}"
owner: "{{owner}}"
quarter: "{{quarter}}"
status: active
created: "{{created}}"
revised: ""
weeks_remaining: {{weeks_remaining}}
---

# {{title}}

**Rock:** {{rock_id}} — {{rock_title}}
**Owner:** {{owner}} | **Due:** {{due}} | **Weeks:** {{weeks_remaining}}

## Weekly Plan

### Week 1 ({{week_1_dates}}) — {{week_1_theme}}
| Task | Owner | Due | Depends On | Milestone |
|------|-------|-----|------------|-----------|
{{week_1_tasks}}

### Week 2 ({{week_2_dates}}) — {{week_2_theme}}
| Task | Owner | Due | Depends On | Milestone |
|------|-------|-----|------------|-----------|
{{week_2_tasks}}

### Weeks 3-6 — {{phase_2_theme}}
{{phase_2_tasks}}

### Weeks 7+ — {{phase_3_theme}}
{{phase_3_tasks}}

## Dependencies & Handoffs

| From | To | What | By When |
|------|-----|------|---------|
{{dependencies}}

## Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
{{risks}}

## Tracking

- **Dashboard:** {{dashboard_metric}}
- **Manual:** {{manual_metric}}
- **L10 check-in:** Rock owner reports on/off track weekly; plan progress reviewed monthly

## Notes
- {{created}}: Plan created
