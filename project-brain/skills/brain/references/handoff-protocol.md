# Handoff Protocol

Use this whenever context is about to be lost, the model changes, or the user asks for a durable project handoff.

## Handoff target

Update `.brain/state/session-brief.md`.

Keep it concise. The next model should be able to read it in under two minutes.

## Template

```markdown
# Session Brief

Updated: YYYY-MM-DD HH:MM

## Project purpose

## Current state

## Architecture map

## Active workstream

## Decisions made recently

## Files changed this session

## Brain pages changed this session

## Known risks / contradictions

## What to read next

1. `.brain/CLAUDE.md`
2. `.brain/wiki/index.md`
3. `graphify-out/GRAPH_REPORT.md` if present
4. <specific wiki/source/code files>

## Next actions

- [ ] ...
```

## MemPalace diary

If MemPalace is available, write a diary entry with:

- what changed
- why it changed
- decisions and preferences
- what the next session should remember

## Log entry

Append to `.brain/log/YYYYMMDD.md`:

```markdown
## [HH:MM] handoff | updated session brief
- Updated `.brain/state/session-brief.md`
- Recorded decisions: ...
- Next action: ...
```
