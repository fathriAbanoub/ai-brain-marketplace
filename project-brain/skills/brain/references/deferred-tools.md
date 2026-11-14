# Deferred Tools (loading tool schemas before first use)

## The harness fact

Tools that are not in the session's tool list may still be **deferred**: they
appear only as names in an `<available-deferred-tools>` list, and calling one
unloaded fails with an error telling you to load it first. A name in that list
means the tool EXISTS in this session — it is just not loaded yet.

Availability is therefore a two-way check:

- tool present in the tool list → available, call it;
- tool named in the deferred-tools list → available after loading, load then call;
- in NEITHER list → genuinely unavailable; say so and continue without it.

## How to load a deferred schema

Use the tool-search tool (it is a tool, not a shell command). Its input takes
BOTH `query` AND `max_results`. `query: "select:Name1,Name2"` fetches those
exact tools by name in ONE call — prefer it over keyword search whenever you
know the names, and load every tool a step needs in that one call:

```text
ToolSearch  query: select:mcp__plugin_mempalace_mempalace__mempalace_status,mcp__plugin_mempalace_mempalace__mempalace_list_wings
            max_results: 5
```

- Full names carry a harness-specific prefix. For this plugin's MemPalace
  install it is commonly `mcp__plugin_mempalace_mempalace__` + the short name,
  so the short name alone (`mempalace_status`) does NOT match.
- The result returns the matched tools' complete JSONSchema definitions inside
  a `<functions>` block. Success = the names you asked for appear there; once
  a tool's schema is in that block it is callable exactly like any tool in the
  tool list.
- A name you asked for that is NOT in the `<functions>` block did not load —
  re-check its exact spelling in the deferred list and retry ONCE, then stop
  and report the tool and the exact error. [unverified] the no-match response
  format was not captured live; judge success only by the names in the block,
  never by the absence of an error.

## Verify with the tool itself

For MemPalace the verification call is `mempalace_status`: it confirms the
layer is reachable and reports index health. A failing call is a REAL failure
— report it with the tool name and the error, and continue from the other
layers.

## Never probe, never fake

- Never probe availability with shell, node, or pip (no `echo "tool present"`,
  no `require(...)`, no import checks). Those prove nothing about the session's
  MCP connections.
- Never write a check that always succeeds. If you cannot name the failure you
  are checking for, you are not checking.
- Never build a workaround client to reach a tool that is absent.

## This rule covers every tool

The same policy applies to ANY tool you need and do not see — MemPalace MCP,
graphify MCP, Obsidian MCP, or built-ins such as `TaskCreate`: check the tool
list and the deferred list, load deferred schemas before first use, call the
tool, and report real errors. Availability is decided by those two lists and
by the tool's own response — never by a name alone, and never by a probe.

Details on MemPalace's own tool set: `references/mempalace-tools.md`.
