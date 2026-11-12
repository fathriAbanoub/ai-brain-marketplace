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

Draft pages are exempt from the source requirement; a source means a
`sources:` frontmatter entry or an inline `{{src ...}}` citation.

This is calculable by `project-brain-lint` and summarized by `project-brain-doctor`.

## Freshness score (0-100)

Percentage of wiki pages updated in the last 30 days, adjusted for stale operational artifacts:

- session brief older than 7 days deducts health,
- graphify report older than 14 days deducts health.

Use frontmatter `updated:` when present. Fall back to file modification time.

## Coverage score (0-100)

Weighted percentage of inventory units covered, from `.brain/inventory.json`
(built by `project-brain-inventory <root> inventory`). A unit is covered when
at least one non-draft wiki page with a substantive body cites it with a
lint-valid `{{src ...}}` citation. Tiers are weighted core 5 / important 3 /
reference 1; the strict gate requires all core units covered and weighted
coverage ≥ 0.90. No inventory → 0, with the command that produces it — absent
data is never scored as 100.

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
  Completeness:   81/100  (17/21 pages fully formed (active pages need a source or citation; structure-only weighted score 88%))
  Freshness:      65/100  (session brief 9 days old, graphify 22 days old)
  Coverage:       70/100  (14/20 units covered, weighted 70% (core uncovered: 2))
  Memory sync:    75/100  (MemPalace last written 2 sessions ago) [estimated from logs]
```

