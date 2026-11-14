# Wing Ownership

Why some MemPalace wings belong to a project brain — and which only look like they do. This file is the rationale: the rules themselves now execute in `scripts/mempalace_reset.py::classify_wings`, which the reset skill runs through `project-brain-reset <project-root> --classify-wings`. Read this for the why; never hand-derive a class the script can compute.

## Why wing ownership is hard

Init records the wing name in `.brain/CLAUDE.md` **before** mining runs, so the recorded name can belong to a wing that does not exist (a failed mine leaves the name behind). And the palace is shared: it holds many wings that are not this brain's — directory-derived wings, other projects' wings, diaries written by other agents. A wing name that looks right is a lead, not a conclusion; ownership comes from the recorded identity plus the user's confirmation, never from the name alone.

## The classes

`classify_wings` is pure and deterministic. It compares each actual wing's normalized name (`normalize_wing_for_compare`: lowercase, `-` and space → `_`, edge separators stripped; runs are NOT collapsed) against the recorded identity. First match wins; equality means equal normalized strings, never prefix or substring. Several actual wings can share one normalized form (for example `wiki-demo-app` and `wiki_demo_app`): every wing stays its own row, and all rows sharing a key are flagged (`FLAG_COLLISION`) — never collapsed. The class constants, named here so drift between script and docs is checkable:

| Class | Constant | Definition |
| --- | --- | --- |
| brain wiki wing | `CLASS_BRAIN_WIKI` | normalized name equals the normalized recorded wiki wing (`mempalace_wing` in `.brain/CLAUDE.md`). New brains (0.9.4+): `wiki_<slug>_<UTC timestamp>`; legacy: bare `wiki_<slug>` or hyphenated `wiki-<slug>` (formats in `mempalace-tools.md`, "Wing Naming Constants"). Holds the compiled wiki pages mined from `.brain/wiki/`. |
| brain diary wing | `CLASS_BRAIN_DIARY` | normalized name equals the normalized diary wing of the recorded agent (`wing_<mempalace_diary_agent>`). The recorded agent defines the brain's diary; a wing `wing_<project slug>` is **not** the brain's diary unless the recorded agent is exactly that. Holds the brain's session-continuity entries. |
| orphan candidate | `CLASS_ORPHAN_CANDIDATE` | wiki-family name for this project's slug (scan below) — "possible orphans of this brain", never deletion targets until the user confirms each by exact name. |
| directory-derived wing | `CLASS_DIRECTORY_DERIVED` | normalized name equals the normalized project directory name. MemPalace mines a project root without `--wing` into this wing, and its session stop hook re-creates it when `MEMPAL_DIR` is set. Holds mined project files or session transcripts, never compiled brain wiki pages. |
| session or path wing | `CLASS_SESSION_OR_PATH` | the raw name starts with a hyphen (harness path-style wings — checked on the raw name because normalization strips edge separators), or the normalized name is a generic session wing (`sessions`, `wing_sessions`). |
| other diary | `CLASS_OTHER_DIARY` | starts with the `wing_` diary prefix and did not match the brain diary wing: written by some other agent or hook. |
| other | `CLASS_OTHER` | everything else, including other projects' wings and test leftovers. |

Outcome letters: **A** when any brain wiki or brain diary wing is present; else **B** when any orphan candidate exists; else **C** — nothing brain-owned. What to do for each outcome is in the reset skill, Step 2; a collision flag forces a per-wing question and never changes the letter.

## The orphan scan

Run only when the recorded wing is absent from the palace (or nothing is recorded): it surfaces wiki-family wings whose normalized name matches this project's slug.

```
wiki_<slug>[_<timestamp>[_<n>]]
```

- `<slug>` comes from the recorded wiki wing (wiki prefix and timestamp/collision tail stripped) when that parses as a wiki-family name, else from the normalized project directory name.
- `<timestamp>` is the documented format `%Y%m%dT%H%M%SZ` (UTC) or the higher-precision form with microseconds; `<n>` is the numeric collision suffix — the forms `generate_wiki_wing_name` produces (see `mempalace-tools.md`, "Wing Naming Constants"). The two legacy bare forms (`wiki_<slug>`, `wiki-<slug>`) normalize to `wiki_<slug>` and are covered by the same pattern.
- A wing without the `wiki_` prefix can never be an orphan candidate, and the directory-derived wing is never one.
- The timestamp is never reconstructed from the brain's creation date: it is already part of the recorded name, and `.brain/CLAUDE.md` only carries a day-level date. The scan shortlists candidates; only the user can confirm one.

## Leftover-wing check (Initialize, new brains only)

Run right after a NEW brain's init (skip on re-init — an existing brain keeps its recorded wing). Init records the wing name before mining runs, and older brains may have used the same names, so leftovers can predate the new brain:

1. Read the recorded `mempalace_wing` (and `mempalace_diary_agent`) from the new `.brain/CLAUDE.md` first — the recorded identity drives the check, never a name pattern.
2. Call `mempalace_status`, then `mempalace_list_wings` (status first: a failing memory layer ends the check honestly instead of half-reporting).
3. If any wing matches the recorded identity — exact name, normalized legacy form, the brain diary wing, or the directory-derived wing — tell the user these predate the new brain and offer cleanup via `/project-brain:reset`. Show each matched wing separately with its exact name and drawer count: distinct names can normalize identically, so every actual wing stays its own row.
4. Also check `mempalace_list_tunnels` / `mempalace_list_hallways` for records naming the recorded wing; report any found.
5. Do not delete anything unasked. Ownership questions are decided by the user, per the classes above.
