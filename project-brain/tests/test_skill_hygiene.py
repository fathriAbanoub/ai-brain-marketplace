"""0.10.0 skill-hygiene tests (findings 1, 2, 3, 5, 6, 8).

Behavior/structure pins, not phrase trivia:
- brain/SKILL.md size ceiling (token economy: the skill is re-sent every turn).
- Every reference named by a skill exists (a dangling "read X" trigger sends a
  weak model hunting, or worse, inventing the file).
- Exactly one authoritative init lifecycle (two competing procedure lists made
  the agent follow the first and silently skip the rest — observed live).
- No skill text decides tool availability from the tool list alone (deferred
  tools made that check report a false "absent" — observed live).
- Graphify docs: skill-primary policy, CLI fallback with GRAPHIFY_BACKEND=none
  on both extract and cluster-only, and the 10 graphify-mcp tool names.
"""

import re
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = PLUGIN_ROOT / "skills"
BRAIN_SKILL = SKILLS_DIR / "brain" / "SKILL.md"
BRAIN_REFS = SKILLS_DIR / "brain" / "references"
SCAFFOLD = PLUGIN_ROOT / "scripts" / "scaffold_brain.py"

# ponytail: ceiling named constant — the 0.9.4 skill was 39,501 bytes with the
# plugin-root fallback duplicated twice and per-mode detail duplicating
# brain-lifecycle.md. 0.10.0 removed the duplication; the remainder is the
# pinned fallback chain plus one non-duplicated procedure per mode. Ceiling
# sits just above the rewritten size so regressions are caught, and any
# future addition must remove something else first.
MAX_SKILL_MD_CHARS = 24000

REFERENCE_NAME_RE = re.compile(r"references/([a-z0-9-]+\.md)")

# The 10 tools graphify-mcp exposes (per the 0.10.0 policy decision; server
# version graphify 0.9.92+). Names here are short forms — the deferred full
# names carry the server's mcp__ prefix.
GRAPHIFY_MCP_TOOLS = (
    "query_graph",
    "get_node",
    "get_neighbors",
    "get_community",
    "god_nodes",
    "graph_stats",
    "shortest_path",
    "get_pr_impact",
    "list_prs",
    "triage_prs",
)


def skill_md_files() -> list[Path]:
    return sorted(SKILLS_DIR.glob("*/SKILL.md"))


def all_skill_docs() -> list[Path]:
    return sorted(SKILLS_DIR.rglob("*.md"))


class TestSizeCeiling:
    def test_brain_skill_within_ceiling(self):
        size = BRAIN_SKILL.stat().st_size
        assert size <= MAX_SKILL_MD_CHARS, (
            f"brain/SKILL.md is {size} bytes; ceiling is {MAX_SKILL_MD_CHARS}. "
            "The skill is re-injected on every turn, so growth must come from "
            "deletions or from a references/ file with a read trigger."
        )


class TestReferencesExist:
    def test_every_named_reference_exists(self):
        missing = []
        for doc in all_skill_docs():
            for name in REFERENCE_NAME_RE.findall(doc.read_text(encoding="utf-8")):
                if not (BRAIN_REFS / name).is_file():
                    missing.append(f"{doc.relative_to(PLUGIN_ROOT)}: references/{name}")
        assert not missing, "Named references that do not exist:\n" + "\n".join(missing)

    def test_new_references_exist(self):
        assert (BRAIN_REFS / "deferred-tools.md").is_file()
        assert (BRAIN_REFS / "edit-discipline.md").is_file()


class TestSingleAuthoritativeLifecycle:
    def test_one_initialize_and_one_work_loop_heading(self):
        text = BRAIN_SKILL.read_text(encoding="utf-8")
        assert len(re.findall(r"^## Initialize\b", text, re.M)) == 1
        assert len(re.findall(r"^## Work loop\b", text, re.M)) == 1
        # The old competing procedure headings must not return.
        assert "## Operating loop" not in text
        assert "## Required first move" not in text

    def test_lifecycle_reference_has_one_initialize(self):
        text = (BRAIN_REFS / "brain-lifecycle.md").read_text(encoding="utf-8")
        assert len(re.findall(r"^### Initialize\b", text, re.M)) == 1

    def test_wiki_schema_read_before_first_write(self):
        text = BRAIN_SKILL.read_text(encoding="utf-8")
        assert "Before the first" in text and "references/wiki-schema.md" in text, (
            "the skill must require reading references/wiki-schema.md before "
            "the first wiki write of a session (observed live: pages written "
            "without the schema invented fields and citations)"
        )


class TestAvailabilityNotToolListOnly:
    def test_no_tool_list_only_availability_check(self):
        """The old Contract 1 decided availability by scanning the tool list
        for `__mempalace_*` suffixes — a false "absent" under deferral. That
        pattern must never return."""
        for doc in all_skill_docs():
            text = doc.read_text(encoding="utf-8")
            assert "tool list for names ending in" not in text, (
                f"{doc.relative_to(PLUGIN_ROOT)}: tool-list-only availability "
                "check must not return (deferred tools are absent from the "
                "tool list by design)"
            )

    def test_deferred_aware_availability_documented(self):
        for path in (BRAIN_SKILL, SKILLS_DIR / "reset" / "SKILL.md", SCAFFOLD):
            text = path.read_text(encoding="utf-8")
            assert "deferred" in text.lower(), (
                f"{path.relative_to(PLUGIN_ROOT)}: must document deferred-tool "
                "availability (tool list OR deferred-tools list)"
            )

    def test_deferred_tools_reference_documents_loading(self):
        text = (BRAIN_REFS / "deferred-tools.md").read_text(encoding="utf-8")
        assert "select:" in text
        # The tool-search tool's own schema requires BOTH parameters.
        assert "max_results" in text
        # Success criterion is the <functions> block, not an empty result or
        # an unsourced error string.
        assert "<functions>" in text
        assert "No matching deferred tools found" not in text, (
            "unsourced error string must not return (quoted as fact in 0.10.0)"
        )
        assert "one name per query" not in text
        assert "Never probe" in text
        assert "TaskCreate" in text, (
            "the generic ANY-tool rule must name a non-MCP example"
        )


class TestEditDisciplineReference:
    def test_read_before_edit_rules_documented(self):
        text = (BRAIN_REFS / "edit-discipline.md").read_text(encoding="utf-8")
        assert "immediately before every Edit" in text
        assert "after compaction" in text
        assert "parallel" in text.lower()
        assert "Write" in text


class TestToolSearchContract:
    """Fix-up round: the tool-search tool requires BOTH `query` and
    `max_results`, and one comma-separated `select:` query loads every tool a
    step needs. The old text taught one name per query and an unsourced
    error string, so agents burned one call per tool and misread failures."""

    TOOLSEARCH_DOCS = (
        BRAIN_SKILL,
        BRAIN_REFS / "deferred-tools.md",
        BRAIN_REFS / "mempalace-workflow.md",
        BRAIN_REFS / "graphify-workflow.md",
        SKILLS_DIR / "reset" / "SKILL.md",
        SCAFFOLD,
    )

    def test_max_results_in_every_toolsearch_doc(self):
        for path in self.TOOLSEARCH_DOCS:
            text = path.read_text(encoding="utf-8")
            assert "select:" in text, f"{path}: select: form missing"
            assert "max_results" in text, (
                f"{path}: every ToolSearch teaching must pass max_results "
                "(the tool's input schema requires BOTH query and max_results)"
            )

    def test_one_name_per_query_removed_everywhere(self):
        for doc in all_skill_docs() + [SCAFFOLD]:
            text = doc.read_text(encoding="utf-8")
            assert "one name per query" not in text, doc
            assert "one name per call" not in text, doc

    def test_initialize_loads_the_six_tools_in_one_call(self):
        text = BRAIN_SKILL.read_text(encoding="utf-8")
        init = text[text.index("## Initialize"):text.index("## Other modes")]
        assert "ONE ToolSearch call" in init
        for short in (
            "mempalace_status",
            "mempalace_list_wings",
            "mempalace_list_tunnels",
            "mempalace_list_hallways",
            "mempalace_get_taxonomy",
            "mempalace_diary_write",
        ):
            assert short in init, f"Initialize must batch-load {short}"

    def test_batch_select_example_present(self):
        """The canonical example must show a comma-separated select: list."""
        text = (BRAIN_REFS / "deferred-tools.md").read_text(encoding="utf-8")
        m = re.search(r"select:[^\n`]*,", text)
        assert m, "deferred-tools.md must show a comma-separated select: example"


class TestIndexRegenerationPhrasing:
    """Fix-up round: 'update the index' contradicted Contract 9 and the
    post-wiki loop — index.md is script-generated, so every phrase must name
    the script (project-brain-lint --reindex), never a hand update."""

    def test_no_update_the_index_phrases(self):
        docs = all_skill_docs() + [SCAFFOLD]
        for doc in docs:
            text = doc.read_text(encoding="utf-8")
            for m in re.finditer(r"(?i)update (the )?index", text):
                line = text[m.start():text.find("\n", m.start())]
                assert "--reindex" in line, (
                    f"{doc.relative_to(PLUGIN_ROOT)}: 'update the index'-style "
                    f"phrase without the --reindex script: {line.strip()[:100]}"
                )

    def test_reindex_command_documented_in_skill_and_reference(self):
        for path in (BRAIN_SKILL, BRAIN_REFS / "brain-lifecycle.md",
                     BRAIN_REFS / "post-wiki-checklist.md", SCAFFOLD):
            assert "--reindex" in path.read_text(encoding="utf-8"), path


class TestGraphifySkillClaimLabeling:
    def test_no_extra_packages_claim_is_labeled_reported(self):
        """'No extra packages / no API key' was the maintainer's reported
        setup, not a verified fact — the docs must say so. The labeled-claim
        pin is whitespace-normalized (prose reflows must not break it)."""
        for path in (BRAIN_SKILL, BRAIN_REFS / "graphify-workflow.md"):
            text = " ".join(path.read_text(encoding="utf-8").split())
            assert "no extra" not in text.lower(), (
                f"{path}: the unverified 'no extra packages' claim must not return"
            )
            assert "no api key" not in text.lower(), (
                f"{path}: the unverified 'no API key' claim must not return"
            )
            assert "verify on first use" in text, (
                f"{path}: the semantic-pass setup must be labeled reported/verify"
            )


class TestInitializeInProgressBrief:
    def test_initialize_writes_in_progress_brief_after_step_2(self):
        text = BRAIN_SKILL.read_text(encoding="utf-8")
        init = text[text.index("## Initialize"):text.index("## Other modes")]
        step2 = init[init.index("2. Read the files it created"):init.index("\n3. ")]
        assert "IN-PROGRESS" in step2, (
            "Initialize must write an IN-PROGRESS session-brief.md right "
            "after init (the run can be cut at any moment)"
        )


class TestGraphifyDocsPolicy:
    def test_skill_primary_cli_fallback(self):
        text = (BRAIN_REFS / "graphify-workflow.md").read_text(encoding="utf-8")
        assert "PRIMARY" in text and "/graphify" in text
        assert "FALLBACK" in text, "the CLI must be labeled fallback-only"
        assert "`/graphify` is a skill invocation, not a shell command" in text, (
            "the skill form must be explicitly marked as non-shell (the old "
            "bash-typing hazard)"
        )

    def test_cli_fallback_documents_backend_env_var(self):
        text = (BRAIN_REFS / "graphify-workflow.md").read_text(encoding="utf-8")
        for sub in ("extract", "cluster-only"):
            assert re.search(
                rf"GRAPHIFY_BACKEND=none.+?`{sub}`|`{sub}`.+?GRAPHIFY_BACKEND=none",
                text, re.DOTALL,
            ), f"GRAPHIFY_BACKEND=none must be tied to `{sub}`"

    def test_mcp_tool_list_matches_server(self):
        text = (BRAIN_REFS / "graphify-workflow.md").read_text(encoding="utf-8")
        for tool in GRAPHIFY_MCP_TOOLS:
            assert f"`{tool}`" in text, f"graphify-mcp tool `{tool}` undocumented"
        assert "reconnect" in text.lower(), (
            "the server reads the graph at startup, so the reconnect step "
            "after any change to graph.json must be documented"
        )
        # Documented CLI equivalents (fallback mapping).
        for mapping in ("graphify query", "graphify path", "graphify explain"):
            assert mapping in text


class TestWikiSchemaAuthoringRules:
    def test_reliability_field_scope_documented(self):
        text = (BRAIN_REFS / "wiki-schema.md").read_text(encoding="utf-8")
        assert "ONLY on `wiki/sources/*`" in text
        assert "plain path string" in text

    def test_index_never_hand_edited(self):
        text = (BRAIN_REFS / "wiki-schema.md").read_text(encoding="utf-8")
        assert "Never hand-edit `index.md`" in text
        assert "--reindex" in text

    def test_minimal_valid_page_documented(self):
        text = (BRAIN_REFS / "wiki-schema.md").read_text(encoding="utf-8")
        assert "## Minimal valid page" in text
        assert '{{src src/render/daemon.ts:40-48 "class RenderDaemon"}}' in text
        assert "wikilinks target wiki pages only" in text.lower()

    def test_line_refs_must_be_verified(self):
        text = (BRAIN_REFS / "wiki-schema.md").read_text(encoding="utf-8")
        assert "grep -n" in text and "never copy line numbers" in text.lower()
