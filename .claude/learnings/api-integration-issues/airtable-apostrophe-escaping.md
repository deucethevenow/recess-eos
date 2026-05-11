---
module: Airtable Integration
date: 2026-04-26
problem_type: api_escaping_error
component: airtable_client
symptoms: ["Airtable API returned 422 on filterByFormula", "Apostrophe in attendee name broke transcript pull", "SQL-style doubled quotes used instead of backslash"]
root_cause: wrong_escape_syntax
severity: high
tags: [airtable, escaping, apostrophe, filterByFormula, fireflies, transcript]
affected_files: [scripts/lib/airtable_client.py]
resolution_type: code_fix
elevated_to_critical: true
---
# Use backslash escaping for Airtable apostrophes

## What the agent does wrong

Uses SQL-style doubled quotes for apostrophes in Airtable `filterByFormula`:

```python
# WRONG — SQL-style escaping, Airtable returns 422
formula = f"FIND('{name.replace(\"'\", \"''\")}')"

# WRONG — forgot to escape backslash first
formula = f"FIND('{name.replace(\"'\", \"\\'\")}', {{Title}})"
```

## Why it's wrong

Airtable uses backslash escaping (`\'`), not SQL-style doubled quotes (`''`). Also, backslash itself must be escaped FIRST, before the apostrophe — otherwise the replacement order corrupts the string.

## Correct pattern

```python
# RIGHT — escape backslash FIRST, then apostrophe
safe_name = name.replace("\\", "\\\\").replace("'", "\\'")
formula = f"FIND('{safe_name}', {{Title}})"
```

## Prevention

- Integration test with `@pytest.mark.integration` hitting real Airtable with apostrophe-bearing input
- The escape order (backslash first, then apostrophe) is critical and easy to get backwards
