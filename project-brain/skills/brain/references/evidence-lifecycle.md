# Evidence Lifecycle

The raw layer should be curated. Do not let `.brain/raw/` become an unreviewed dumping ground.

## Ingestion standards

Store a source in `.brain/raw/` when it is likely to be useful again, supports a durable claim, or may need verification later.

Good candidates:

- project specs,
- design docs,
- architecture notes,
- meeting notes with decisions,
- important articles or papers,
- API docs,
- customer/user research,
- source material that could contradict future claims.

Do not store raw evidence when:

- the user only gave a passing instruction,
- the content is trivial and fully captured by a wiki edit,
- the source is a secret or credential,
- the source is too large to store safely,
- a pointer file is enough.

## Pointer file format

For large, binary, external, or frequently changing sources, create a pointer file under `.brain/raw/refs/`.

```yaml
title: <source title>
source_url: <url or external location>
stored_at: <where the real source lives>
added_date: YYYY-MM-DD
summary: <1-3 sentence summary>
key_claims:
  - <claim 1>
  - <claim 2>
trust_level: high|medium|low|unknown
review_status: unreviewed|summarized|verified|superseded
```

Below the YAML, add notes about why the source matters and which wiki pages cite it.

## Evidence aging

Sources older than 90 days with no wiki references should be flagged as `suggest`-level candidates for archival by lint.

Archival does not mean deletion. It means:

- add `review_status: stale` or `superseded`,
- move to an archive subfolder if appropriate,
- update wiki pages that still cite old claims,
- log the decision.

## Contradiction protocol

When two raw sources disagree, do not hide the conflict. Record it in `.brain/wiki/open-questions.md` or a dedicated contradiction page.

Use this format:

```markdown
## Conflict: <short title>

- Claim: <claim>
  - Source: `<path>`
  - Evidence: <brief quote or summary>
- Counter-claim: <counter-claim>
  - Source: `<path>`
  - Evidence: <brief quote or summary>
- Higher-trust source: <path or unknown>
- Reason: <why this source is trusted more>
- Verification needed: <what would resolve it>
- Status: open|resolved|superseded
```

After resolving, update every affected wiki page and log the resolution.

