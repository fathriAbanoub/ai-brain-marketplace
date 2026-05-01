# Brain Health Metrics

Use measurable health metrics instead of vague judgments.

## Completeness score (0-100)

Percentage of wiki pages that have all of:

- title,
- `type`,
- `status`,
- at least one source,
- at least one wikilink to another page,
- an entry in `.brain/wiki/index.md`.

This is calculable by `project-brain-lint` and summarized by `project-brain-doctor`.

## Freshness score (0-100)

Percentage of wiki pages updated in the last 30 days, adjusted for stale operational artifacts:

- session brief older than 7 days deducts health,
- graphify report older than 14 days deducts health.

Use frontmatter `updated:` when present. Fall back to file modification time.

## Coverage score (0-100)

Percentage of project source files in `.brain/raw/` that have a corresponding wiki source summary page.

A raw source is covered when a page in `.brain/wiki/sources/` cites or names the raw file path, pointer file, or source title.

## Memory sync score (0-100)

Whether MemPalace has been written to in the recent working history.

Target behavior:

- 100 — diary/preference written in the latest substantial session,
- 75 — written within the last 2 sessions,
- 50 — written within the last 3 sessions,
- 25 — older evidence of memory sync,
- 0 — no evidence of MemPalace sync.

Agents should prefer real MemPalace diary search when available. Scripts can estimate from `.brain/log/` entries that mention MemPalace diary/preference writes.

**Limitation:** The script estimates memory sync from `.brain/log/` entries that mention MemPalace diary or preference writes. This is a heuristic. Real confirmation requires calling `mempalace_search` from an active agent session. The score is marked `[estimated]` in doctor output.

## Total score

Total brain health is the rounded average of completeness, freshness, coverage, and memory sync.

Example:

```text
Project Brain Health: 73/100
  Completeness:   81/100  (17/21 pages fully formed)
  Freshness:      65/100  (session brief 9 days old, graphify 22 days old)
  Coverage:       70/100  (7/10 raw sources have wiki summaries)
  Memory sync:    75/100  (MemPalace last written 2 sessions ago) [estimated from logs]
```

