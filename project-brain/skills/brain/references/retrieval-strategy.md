# Retrieval Strategy

## Why retrieval routing matters

Always starting with the wiki is wrong. The wiki is compiled synthesis, so it can lag behind raw reality. For code questions, graphify has already extracted structure and relationships. For session questions, the session brief has the current state. Routing to the wrong layer first wastes turns and increases the chance of stale answers.

## Layer strengths and blind spots

| Layer | Best for | Worst for | Staleness risk |
|---|---|---|---|
| session-brief | current state, active task, immediate next steps | anything more than 400 words ago | high — must be updated every session |
| wiki/decisions | why choices were made, options considered | current implementation details | medium — updated when decisions change |
| wiki/architecture | system structure, component roles | live code state | medium — lags code changes |
| wiki/concepts | definitions, terminology, project-specific meanings | code navigation | low — stable once written |
| MemPalace | user preferences, verbatim session recall, emotional/social context | factual source verification | low — persistent across resets |
| graphify | code structure, dependency maps, bridge files, god nodes | prose understanding, decisions | high — must be rebuilt after code changes |
| raw sources | ground truth verification, contested claims | fast lookup | none — immutable |

## Multi-layer questions

When a question spans layers, such as "why did we build the pipeline this way and how does it connect?", use a two-pass strategy:

1. Pass 1: answer the "why" from MemPalace and wiki decision pages.
2. Pass 2: answer the "how does it connect" from graphify and architecture pages.
3. Merge the findings and cross-check before responding.

## Confidence thresholds

- **High confidence:** two independent layers agree.
- **Medium confidence:** one layer answers but is not verified by another. State the confidence level explicitly.
- **Low confidence:** only chat context or current-turn inference supports the answer. Mark it as unverified and add it to open questions.

## When to promote an answer

If a query answer required three or more layer lookups to resolve, that answer is valuable enough to save. Store it under `.brain/outputs/queries/YYYY-MM-DD-<slug>.md` or promote it into a wiki page if the answer is durable.
