# Obsidian Workflow

The user's Obsidian MCP is connected. Use it to mirror selected brain wiki pages to the user's Obsidian vault when requested.

## Source of truth

`.brain/wiki/` is the source of truth. Obsidian is a view layer for human browsing, graph view, and annotation.

Always write to `.brain/wiki/` first. Mirror to Obsidian only after the local brain page is correct.

## When to use Obsidian MCP tools

Use Obsidian MCP when the user asks to:

- "open in Obsidian",
- "save to vault",
- "view in Obsidian",
- "sync the brain to Obsidian",
- "browse this in the vault",
- use Obsidian graph view for the brain.

Do not sync automatically.

## Tool mapping

Use the Obsidian MCP tool names exposed in the current session. Map by capability:

- **Read**: tools with names such as `obsidian_read`, `obsidian_get`, `obsidian_get_file`, or `obsidian_get_file_contents`.
- **Write/create/update**: tools with names such as `obsidian_write`, `obsidian_create`, `obsidian_update`, `obsidian_patch`, or `obsidian_append`.
- **Search/list**: tools with names such as `obsidian_search`, `obsidian_list`, or `obsidian_find`.
- **Move/rename**: tools with names such as `obsidian_move`, `obsidian_rename`, or `obsidian_delete` when deletion is explicitly requested.

Before writing, search/list the destination path so the agent does not accidentally duplicate pages.

## Sync direction

1. Update `.brain/wiki/` first.
2. Identify changed pages since the last sync from `.brain/log/`.
3. Mirror changed wiki pages to Obsidian.
4. Log the sync.

Never treat edits made directly in Obsidian as automatically authoritative. If the user edits in Obsidian and wants those changes preserved, pull them back into `.brain/wiki/` deliberately.

## Vault path convention

Mirror project wiki pages to:

```text
<vault>/project-brains/<project-name>/
```

Keep the same relative structure beneath that folder. Example:

```text
.brain/wiki/architecture/System Overview.md
→ <vault>/project-brains/<project-name>/architecture/System Overview.md
```

This avoids collisions with the user's personal notes.

## Wikilinks

The brain wiki already uses `[[WikiLink]]` syntax, which is Obsidian-native. Preserve wikilinks exactly. Do not convert them to markdown links unless the user asks.

## What not to sync by default

Do not sync these unless explicitly requested:

- `.brain/raw/`
- `.brain/log/`
- `.brain/audit/`
- `.brain/state/`
- `.brain/memory/`
- `.brain/outputs/`

Raw sources, logs, audit files, and state files are internal brain scaffolding. The vault should receive curated wiki pages.

## Sync log entry

After syncing, append a log entry with:

- timestamp,
- destination vault path,
- pages mirrored,
- pages skipped,
- any conflicts or unresolved tool errors.

