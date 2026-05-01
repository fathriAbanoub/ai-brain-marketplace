# Audit Workflow

The audit folder is the human feedback surface for the brain.

## Directory

```text
.brain/audit/
├── <open-feedback>.md
└── resolved/
    └── <processed-feedback>.md
```

## Feedback file shape

```markdown
---
id: YYYYMMDD-HHMMSS-shortid
target: .brain/wiki/path/page.md
severity: info | suggest | warn | error
author: user
created: YYYY-MM-DDTHH:MM:SS
status: open
---

# Comment

<what is wrong or should change>

# Resolution

<!-- filled by the agent -->
```

## Processing steps

1. Read all open audit files.
2. Process `error` and `warn` before `suggest` and `info`.
3. Locate the target text and verify against raw sources, wiki pages, MemPalace, or graphify as needed.
4. Decide: accept, partially accept, reject, or defer.
5. Update the target page if needed.
6. Add a resolution note.
7. Move the audit file to `.brain/audit/resolved/`.
8. Log the resolution.

Do not delete feedback. Rejected feedback still becomes resolved with a rationale.
