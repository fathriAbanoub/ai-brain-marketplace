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
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = PLUGIN_ROOT / "skills"
BRAIN_SKILL = SKILLS_DIR / "brain" / "SKILL.md"
BRAIN_REFS = SKILLS_DIR / "brain" / "references"
BRAIN_LIFECYCLE = BRAIN_REFS / "brain-lifecycle.md"
WING_OWNERSHIP = BRAIN_REFS / "wing-ownership.md"
SCAFFOLD = PLUGIN_ROOT / "scripts" / "scaffold_brain.py"
SCRIPTS_PATH_INDEX = 0
sys.path.insert(SCRIPTS_PATH_INDEX, str(PLUGIN_ROOT / "scripts"))

from scaffold_brain import BLOCKED_WING_MARKER  # noqa: E402
from mempalace_reset import PAGE_LIMIT  # noqa: E402

# ponytail: ceiling named constant — the 0.9.4 skill was 39,501 bytes with the
# plugin-root fallback duplicated twice and per-mode detail duplicating
# brain-lifecycle.md. 0.10.0 removed the duplication; the remainder is the
# pinned fallback chain plus one non-duplicated procedure per mode. Ceiling
# sits just above the rewritten size so regressions are caught, and any
# future addition must remove something else first.
MAX_SKILL_MD_CHARS = 24000
MIN_INITIALIZE_TUNNEL_CALLS = 2
DIARY_FIELD_LABELS = ("Summary", "Key finding", "Contradictions", "Log", "Next")
INITIALIZE_HEADING = "## Initialize"
OTHER_MODES_HEADING = "## Other modes"
WORK_LOOP_HEADING = "## Work loop"
WIKI_LEDGER_HEADING = "## Wiki ledger"
STRICT_FLAG = "--strict"
INVENTORY_COMMAND = "project-brain-inventory"
BASELINE_DOCTOR_COMMAND = "`project-brain-doctor <project-root>`"
NUMBERED_STEP_END = r"(?=^\d+\. |\Z)"
INITIALIZE_WORK_LOOP_STEP_RE = re.compile(
    rf"^\d+\. (?:\*\*)?Run the `## Work loop` section.*?{NUMBERED_STEP_END}", re.M | re.S,
)
INITIALIZE_LEFTOVER_STEP_RE = re.compile(
    rf"^\d+\. (?:\*\*)?Leftover-wing check.*?{NUMBERED_STEP_END}", re.M | re.S,
)
INITIALIZE_MINING_STEP_RE = re.compile(
    rf"^\d+\. (?:Compile wiki pages|If the brief has).*?{NUMBERED_STEP_END}", re.M | re.S,
)
WORK_LOOP_BRIEF_STEP_RE = re.compile(
    rf"^\d+\. Make progress durable:.*?{NUMBERED_STEP_END}", re.M | re.S,
)
# ponytail: final report is one line; extend the step matcher if it is wrapped.
FINAL_REPORT_STEP_RE = re.compile(r"^\d+\. Final report:[^\n]*", re.M)
FINAL_REPORT_TODO_RULE = "No next-session to-do list for runnable work."
FINAL_REPORT_BLOCKED_WING_CLAUSE = "and the recorded wing is not blocked"
FINAL_REPORT_DRAWERS_CLAUSE = "and the recorded wing has drawers (verified in step 10)"
LIFECYCLE_DONE_DRAWERS_CLAUSE = "the recorded wing is not blocked and it has drawers verified in step 10"
LIFECYCLE_DONE_GATE_RE = re.compile(r"^- The final strict gate exits [^\n]*", re.M)
RE_MINE_SUCCESS_CLAUSE = "every re-mine of step 13's wiki changes succeeded"
RE_MINE_RECIPE_RULE = "re-mine wiki changes (Recipe 3 in `references/mempalace-tools.md`; dry run first)"
RE_MINE_NO_CHANGES_RULE = "No wiki changes in step 13 → no re-mine."
RE_MINE_FAILURE_RULE = "mines/re-mines with their failing commands"
LIFECYCLE_DONE_RE_MINE_FAILURE_RULE = "failed re-mines and their failing commands under **not done**"
TEXT_ENCODING = "utf-8"
LEFTOVER_RESET_OFFER_RULE = "Offer `/project-brain:reset` for wiki/brain-diary matches or orphan candidates."
LEFTOVER_DIRECTORY_RULE = "Directory-derived wings: informational only (MemPalace re-creates them), no cleanup offer."
EDIT_CONTRACT_RE = re.compile(r"^\*\*\d+\. Edit discipline\.\*\*[^\n]*", re.M)
INLINE_EDIT_RULES = (
    "Read the page immediately before every Edit",
    "again after compaction or a failed Edit",
    "Prefer Write for whole-page rewrites",
    "Never batch dependent edits to one file in one parallel turn",
    "Retry an Edit once, then switch to Write",
    "`references/edit-discipline.md`",
)
HALLWAY_TOOL = "mempalace_list_hallways"
HALLWAY_OFFSET_FIELD = "offset"
HALLWAY_START_OFFSET = 0
HALLWAY_PAGING_RULE = (
    f"advance `offset` by {PAGE_LIMIT} until a page returns fewer than {PAGE_LIMIT} records"
)
HALLWAY_START_OFFSET_RE = re.compile(rf"\boffset:\s*{HALLWAY_START_OFFSET}\b")
HALLWAY_PAGE_LIMIT_RE = re.compile(rf"\blimit:\s*{PAGE_LIMIT}\b")
LEFTOVER_RETRY_RULE = "Retry any failed call once"
LEFTOVER_UNVERIFIED_RULE = "if it still fails (name the call and page)"
LEFTOVER_COLLISION_RULE = "or the recorded wiki wing exists"
LEFTOVER_NO_MINE_RULE = "do NOT mine"
LEFTOVER_BLOCK_RULE = (
    f"prepend `{BLOCKED_WING_MARKER} <exact wing name> — "
    "collision or unverified check; do not mine; resolve via /project-brain:reset`"
)
LEFTOVER_PRESERVE_RULE = "to `.brain/state/session-brief.md`, preserving its content"
LEFTOVER_MEMORY_NOT_DONE_RULE = "memory **not done**"
LEFTOVER_SEPARATE_SKIP_CLAUSE = "or the leftover-wing check was unverified"
LEFTOVER_SEPARATE_COMPLETION_CLAUSE = "no leftover-wing check is unverified"
OWNERSHIP_OLD_FAILURE_RULES = ("in-run only", "no new marker")
OWNERSHIP_RESET_ONLY_RULE = "The block holds until `/project-brain:reset` removes the brain."
OWNERSHIP_NO_RECHECK_RULE = "no automatic re-check flow"
OWNERSHIP_HALLWAY_STEP_RE = re.compile(
    rf"^\d+\. Check `mempalace_list_tunnels`.*?{NUMBERED_STEP_END}", re.M | re.S,
)
LAST_STRICT_SCORES_RE = re.compile(r"sub-scores.*last strict run", re.S)
DIARY_FORMAT_POINTER_RE = re.compile(
    r"(?i)diary(?:\s+entry)?\s+(?:format|template)|(?:format|template)\s+(?:for\s+)?diar(?:y|ies)",
)
STEP_RANGE_RE = re.compile(r"\bsteps\s+\d+\s*[–—-]\s*\d+")
WORK_LOOP_RANGE_PREFIX_RE = re.compile(r"Work loop\s*\(?\s*$")
DIARY_LABEL_RE = re.compile(r"^\s*([A-Za-z ]+): \[", re.M)
WIKI_SYNC_RECIPE_RE = re.compile(r"^### \d+\. Sync the Wiki\b.*?(?=^### |\Z)", re.M | re.S)

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
            for name in REFERENCE_NAME_RE.findall(doc.read_text(encoding=TEXT_ENCODING)):
                if not (BRAIN_REFS / name).is_file():
                    missing.append(f"{doc.relative_to(PLUGIN_ROOT)}: references/{name}")
        assert not missing, "Named references that do not exist:\n" + "\n".join(missing)

    def test_new_references_exist(self):
        assert (BRAIN_REFS / "deferred-tools.md").is_file()
        assert (BRAIN_REFS / "edit-discipline.md").is_file()


class TestSingleAuthoritativeLifecycle:
    def test_one_initialize_and_one_work_loop_heading(self):
        text = BRAIN_SKILL.read_text(encoding=TEXT_ENCODING)
        assert len(re.findall(r"^## Initialize\b", text, re.M)) == 1
        assert len(re.findall(r"^## Work loop\b", text, re.M)) == 1
        # The old competing procedure headings must not return.
        assert "## Operating loop" not in text
        assert "## Required first move" not in text

    def test_lifecycle_reference_has_one_initialize(self):
        text = BRAIN_LIFECYCLE.read_text(encoding=TEXT_ENCODING)
        assert len(re.findall(r"^### Initialize\b", text, re.M)) == 1

    def test_wiki_schema_read_before_first_write(self):
        text = BRAIN_SKILL.read_text(encoding=TEXT_ENCODING)
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
            text = doc.read_text(encoding=TEXT_ENCODING)
            assert "tool list for names ending in" not in text, (
                f"{doc.relative_to(PLUGIN_ROOT)}: tool-list-only availability "
                "check must not return (deferred tools are absent from the "
                "tool list by design)"
            )

    def test_deferred_aware_availability_documented(self):
        for path in (BRAIN_SKILL, SKILLS_DIR / "reset" / "SKILL.md", SCAFFOLD):
            text = path.read_text(encoding=TEXT_ENCODING)
            assert "deferred" in text.lower(), (
                f"{path.relative_to(PLUGIN_ROOT)}: must document deferred-tool "
                "availability (tool list OR deferred-tools list)"
            )

    def test_deferred_tools_reference_documents_loading(self):
        text = (BRAIN_REFS / "deferred-tools.md").read_text(encoding=TEXT_ENCODING)
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
    def test_essential_edit_rules_remain_inline(self):
        contract = EDIT_CONTRACT_RE.search(BRAIN_SKILL.read_text(encoding=TEXT_ENCODING))
        assert contract, "Edit discipline contract must remain inline"
        for rule in INLINE_EDIT_RULES:
            assert rule in contract.group(), f"Missing inline edit rule: {rule}"

    def test_read_before_edit_rules_documented(self):
        text = (BRAIN_REFS / "edit-discipline.md").read_text(encoding=TEXT_ENCODING)
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
            text = path.read_text(encoding=TEXT_ENCODING)
            assert "select:" in text, f"{path}: select: form missing"
            assert "max_results" in text, (
                f"{path}: every ToolSearch teaching must pass max_results "
                "(the tool's input schema requires BOTH query and max_results)"
            )

    def test_one_name_per_query_removed_everywhere(self):
        for doc in all_skill_docs() + [SCAFFOLD]:
            text = doc.read_text(encoding=TEXT_ENCODING)
            assert "one name per query" not in text, doc
            assert "one name per call" not in text, doc

    def test_initialize_loads_the_eight_tools_in_one_call(self):
        text = BRAIN_SKILL.read_text(encoding=TEXT_ENCODING)
        init = text[text.index(INITIALIZE_HEADING):text.index(OTHER_MODES_HEADING)]
        batch = init[init.index("ONE ToolSearch call"):init.index("\n5. ")]
        for short in (
            "mempalace_status",
            "mempalace_list_wings",
            "mempalace_list_tunnels",
            "mempalace_list_hallways",
            "mempalace_get_taxonomy",
            "mempalace_diary_write",
            "mempalace_list_rooms",
            "mempalace_mine",
        ):
            assert short in batch, f"Initialize must batch-load {short}"

    def test_initialize_lists_tunnels_after_loading(self):
        text = BRAIN_SKILL.read_text(encoding=TEXT_ENCODING)
        init = text[text.index(INITIALIZE_HEADING):text.index(OTHER_MODES_HEADING)]
        assert init.count("mempalace_list_tunnels") >= MIN_INITIALIZE_TUNNEL_CALLS

    def test_batch_select_example_present(self):
        """The canonical example must show a comma-separated select: list."""
        text = (BRAIN_REFS / "deferred-tools.md").read_text(encoding=TEXT_ENCODING)
        m = re.search(r"select:[^\n`]*,", text)
        assert m, "deferred-tools.md must show a comma-separated select: example"


class TestIndexRegenerationPhrasing:
    """Fix-up round: 'update the index' contradicted Contract 9 and the
    post-wiki loop — index.md is script-generated, so every phrase must name
    the script (project-brain-lint --reindex), never a hand update."""

    def test_no_update_the_index_phrases(self):
        docs = all_skill_docs() + [SCAFFOLD]
        for doc in docs:
            text = doc.read_text(encoding=TEXT_ENCODING)
            for m in re.finditer(r"(?i)update (the )?index", text):
                line = text[m.start():text.find("\n", m.start())]
                assert "--reindex" in line, (
                    f"{doc.relative_to(PLUGIN_ROOT)}: 'update the index'-style "
                    f"phrase without the --reindex script: {line.strip()[:100]}"
                )

    def test_reindex_command_documented_in_skill_and_reference(self):
        for path in (BRAIN_SKILL, BRAIN_LIFECYCLE,
                     BRAIN_REFS / "post-wiki-checklist.md", SCAFFOLD):
            assert "--reindex" in path.read_text(encoding=TEXT_ENCODING), path


class TestGraphifySkillClaimLabeling:
    def test_no_extra_packages_claim_is_labeled_reported(self):
        """'No extra packages / no API key' was the maintainer's reported
        setup, not a verified fact — the docs must say so. The labeled-claim
        pin is whitespace-normalized (prose reflows must not break it)."""
        for path in (BRAIN_SKILL, BRAIN_REFS / "graphify-workflow.md"):
            text = " ".join(path.read_text(encoding=TEXT_ENCODING).split())
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
        text = BRAIN_SKILL.read_text(encoding=TEXT_ENCODING)
        init = text[text.index(INITIALIZE_HEADING):text.index(OTHER_MODES_HEADING)]
        step2 = init[init.index("2. Read the files it created"):init.index("\n3. ")]
        assert "IN-PROGRESS" in step2, (
            "Initialize must write an IN-PROGRESS session-brief.md right "
            "after init (the run can be cut at any moment)"
        )


class TestGraphifyDocsPolicy:
    def test_skill_primary_cli_fallback(self):
        text = (BRAIN_REFS / "graphify-workflow.md").read_text(encoding=TEXT_ENCODING)
        assert "PRIMARY" in text and "/graphify" in text
        assert "FALLBACK" in text, "the CLI must be labeled fallback-only"
        assert "`/graphify` is a skill invocation, not a shell command" in text, (
            "the skill form must be explicitly marked as non-shell (the old "
            "bash-typing hazard)"
        )

    def test_cli_fallback_documents_backend_env_var(self):
        text = (BRAIN_REFS / "graphify-workflow.md").read_text(encoding=TEXT_ENCODING)
        for sub in ("extract", "cluster-only"):
            assert re.search(
                rf"GRAPHIFY_BACKEND=none.+?`{sub}`|`{sub}`.+?GRAPHIFY_BACKEND=none",
                text, re.DOTALL,
            ), f"GRAPHIFY_BACKEND=none must be tied to `{sub}`"

    def test_mcp_tool_list_matches_server(self):
        text = (BRAIN_REFS / "graphify-workflow.md").read_text(encoding=TEXT_ENCODING)
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
        text = (BRAIN_REFS / "wiki-schema.md").read_text(encoding=TEXT_ENCODING)
        assert "ONLY on `wiki/sources/*`" in text
        assert "plain path string" in text

    def test_index_never_hand_edited(self):
        text = (BRAIN_REFS / "wiki-schema.md").read_text(encoding=TEXT_ENCODING)
        assert "Never hand-edit `index.md`" in text
        assert "--reindex" in text

    def test_minimal_valid_page_documented(self):
        text = (BRAIN_REFS / "wiki-schema.md").read_text(encoding=TEXT_ENCODING)
        assert "## Minimal valid page" in text
        assert '{{src src/render/daemon.ts:40-48 "class RenderDaemon"}}' in text
        assert "wikilinks target wiki pages only" in text.lower()

    def test_line_refs_must_be_verified(self):
        text = (BRAIN_REFS / "wiki-schema.md").read_text(encoding=TEXT_ENCODING)
        assert "grep -n" in text and "never copy line numbers" in text.lower()


class TestInitializeGate:
    def test_work_loop_precedes_strict_gate_and_final_report(self):
        text = BRAIN_SKILL.read_text(encoding=TEXT_ENCODING)
        init = text[text.index(INITIALIZE_HEADING):text.index(OTHER_MODES_HEADING)]
        work_loop = INITIALIZE_WORK_LOOP_STEP_RE.search(init)
        assert work_loop, "Initialize must have an explicit Work loop invocation step"
        assert INVENTORY_COMMAND in work_loop.group()
        strict = re.search(STRICT_FLAG, init)
        assert strict, "Initialize must invoke the strict gate"
        assert work_loop.start() < strict.start() < work_loop.end(), (
            "The first strict gate must be inside the Work loop invocation step"
        )
        assert STRICT_FLAG in work_loop.group()
        report = FINAL_REPORT_STEP_RE.search(init)
        assert report, "Initialize must have a final-report step"
        assert strict.start() < report.start()
        _, _, final_scores = work_loop.group().partition(STRICT_FLAG)
        assert LAST_STRICT_SCORES_RE.search(final_scores), (
            "Initialize must report sub-scores from the last strict run in the Work loop step"
        )
        assert BASELINE_DOCTOR_COMMAND not in init[strict.end():]

    def test_final_report_does_not_defer_runnable_work(self):
        for doc in (BRAIN_SKILL, BRAIN_LIFECYCLE):
            report = FINAL_REPORT_STEP_RE.search(doc.read_text(encoding=TEXT_ENCODING))
            assert report, f"{doc}: missing final-report step"
            assert FINAL_REPORT_TODO_RULE in report.group(), (
                f"{doc}: final report must not defer runnable work to a next-session to-do list"
            )

    def test_every_step_13_re_mine_must_succeed_for_completion(self):
        for doc, pattern in (
            (BRAIN_SKILL, FINAL_REPORT_STEP_RE),
            (BRAIN_LIFECYCLE, FINAL_REPORT_STEP_RE),
            (BRAIN_LIFECYCLE, LIFECYCLE_DONE_GATE_RE),
        ):
            gate = pattern.search(doc.read_text(encoding=TEXT_ENCODING))
            assert gate, f"{doc}: missing completion gate"
            assert RE_MINE_SUCCESS_CLAUSE in gate.group(), (
                f"{doc}: completion must require every step 13 re-mine to succeed"
            )
            assert RE_MINE_NO_CHANGES_RULE in gate.group()
            failure_rule = (RE_MINE_FAILURE_RULE if pattern is FINAL_REPORT_STEP_RE
                            else LIFECYCLE_DONE_RE_MINE_FAILURE_RULE)
            assert failure_rule in gate.group()

    def test_step_13_re_mines_use_recipe_3(self):
        for doc in (BRAIN_SKILL, BRAIN_LIFECYCLE):
            text = doc.read_text(encoding=TEXT_ENCODING)
            step = INITIALIZE_WORK_LOOP_STEP_RE.search(text)
            assert step and RE_MINE_RECIPE_RULE in step.group(), doc

    def test_leftover_check_verifies_unique_wiki_wing(self):
        text = BRAIN_SKILL.read_text(encoding=TEXT_ENCODING)
        init = text[text.index(INITIALIZE_HEADING):text.index(OTHER_MODES_HEADING)]
        match = INITIALIZE_LEFTOVER_STEP_RE.search(init)
        assert match, "Initialize must retain the leftover-wing check"
        step = match.group()
        assert "mempalace_list_wings" in step and "tunnel" in step and "hallway" in step
        assert "do NOT mine" in step
        assert LEFTOVER_RESET_OFFER_RULE in step
        assert LEFTOVER_DIRECTORY_RULE in step
        for doc in (BRAIN_SKILL, BRAIN_LIFECYCLE, WING_OWNERSHIP):
            assert "--wing <verified-unique-name>" not in doc.read_text(encoding=TEXT_ENCODING)

    def test_leftover_hallway_checks_page_every_record(self):
        for doc, pattern in (
            (BRAIN_SKILL, INITIALIZE_LEFTOVER_STEP_RE),
            (BRAIN_LIFECYCLE, INITIALIZE_LEFTOVER_STEP_RE),
            (WING_OWNERSHIP, OWNERSHIP_HALLWAY_STEP_RE),
        ):
            step = pattern.search(doc.read_text(encoding=TEXT_ENCODING))
            assert step, f"{doc}: missing hallway-check step"
            assert HALLWAY_TOOL in step.group()
            assert HALLWAY_OFFSET_FIELD in step.group()
            assert HALLWAY_PAGE_LIMIT_RE.search(step.group())
            assert HALLWAY_PAGING_RULE in step.group()
            if pattern is OWNERSHIP_HALLWAY_STEP_RE:
                assert HALLWAY_START_OFFSET_RE.search(step.group())

    def test_unverified_leftover_check_retries_once_and_skips_mining(self):
        for doc, pattern in (
            (BRAIN_SKILL, INITIALIZE_LEFTOVER_STEP_RE),
            (BRAIN_LIFECYCLE, INITIALIZE_LEFTOVER_STEP_RE),
            (WING_OWNERSHIP, OWNERSHIP_HALLWAY_STEP_RE),
        ):
            text = doc.read_text(encoding=TEXT_ENCODING)
            leftover = pattern.search(text)
            assert leftover, f"{doc}: missing leftover-wing check"
            for rule in (LEFTOVER_RETRY_RULE, LEFTOVER_UNVERIFIED_RULE,
                         LEFTOVER_COLLISION_RULE, LEFTOVER_NO_MINE_RULE,
                         LEFTOVER_BLOCK_RULE, LEFTOVER_PRESERVE_RULE,
                         LEFTOVER_MEMORY_NOT_DONE_RULE):
                assert rule in leftover.group(), f"{doc}: missing {rule}"
            if pattern is INITIALIZE_LEFTOVER_STEP_RE:
                mining = INITIALIZE_MINING_STEP_RE.search(text)
                assert mining and BLOCKED_WING_MARKER in mining.group(), doc
                assert LEFTOVER_SEPARATE_SKIP_CLAUSE not in mining.group(), doc
                report = FINAL_REPORT_STEP_RE.search(text)
                assert report and LEFTOVER_SEPARATE_COMPLETION_CLAUSE not in report.group(), doc
                if doc == BRAIN_LIFECYCLE:
                    done_gate = LIFECYCLE_DONE_GATE_RE.search(text)
                    assert done_gate and LEFTOVER_SEPARATE_COMPLETION_CLAUSE not in done_gate.group(), doc

    def test_leftover_block_is_reset_only_not_in_run(self):
        text = WING_OWNERSHIP.read_text(encoding=TEXT_ENCODING)
        for rule in OWNERSHIP_OLD_FAILURE_RULES:
            assert rule not in text, f"wing-ownership.md: remove {rule}"
        step = OWNERSHIP_HALLWAY_STEP_RE.search(text)
        assert step and OWNERSHIP_RESET_ONLY_RULE in step.group()
        assert OWNERSHIP_NO_RECHECK_RULE in step.group()

    def test_blocked_wing_guard_is_carried_through_mining_and_brief_updates(self):
        text = BRAIN_SKILL.read_text(encoding=TEXT_ENCODING)
        init = text[text.index(INITIALIZE_HEADING):text.index(OTHER_MODES_HEADING)]
        work_loop = text[text.index(WORK_LOOP_HEADING):text.index(WIKI_LEDGER_HEADING)]
        for pattern, section in (
            (INITIALIZE_LEFTOVER_STEP_RE, init),
            (INITIALIZE_MINING_STEP_RE, init),
            (WORK_LOOP_BRIEF_STEP_RE, work_loop),
        ):
            step = pattern.search(section)
            assert step, f"Missing guarded step: {pattern.pattern}"
            assert BLOCKED_WING_MARKER in step.group()
        lifecycle = BRAIN_LIFECYCLE.read_text(encoding=TEXT_ENCODING)
        for pattern in (INITIALIZE_LEFTOVER_STEP_RE, INITIALIZE_MINING_STEP_RE):
            step = pattern.search(lifecycle)
            assert step and BLOCKED_WING_MARKER in step.group()
        for section in (init, lifecycle):
            report = FINAL_REPORT_STEP_RE.search(section)
            assert report and FINAL_REPORT_BLOCKED_WING_CLAUSE in report.group()
            assert FINAL_REPORT_DRAWERS_CLAUSE in report.group()
        done_gate = LIFECYCLE_DONE_GATE_RE.search(lifecycle)
        assert done_gate and LIFECYCLE_DONE_DRAWERS_CLAUSE in done_gate.group()
        catalog = (BRAIN_REFS / "mempalace-tools.md").read_text(encoding=TEXT_ENCODING)
        recipe = WIKI_SYNC_RECIPE_RE.search(catalog)
        assert recipe and BLOCKED_WING_MARKER in recipe.group()

    def test_no_diary_format_pointer_to_tool_catalog(self):
        # ponytail: same-line pointers only; extend to paragraphs if references wrap.
        for doc in all_skill_docs():
            for line in doc.read_text(encoding=TEXT_ENCODING).splitlines():
                if "mempalace-tools.md" in line:
                    assert not DIARY_FORMAT_POINTER_RE.search(line), (
                        f"{doc.relative_to(PLUGIN_ROOT)}: diary format points to the tool catalog"
                    )

    def test_step_ranges_are_scoped_to_work_loop(self):
        text = BRAIN_SKILL.read_text(encoding=TEXT_ENCODING)
        init = text[text.index(INITIALIZE_HEADING):text.index(OTHER_MODES_HEADING)]
        for match in STEP_RANGE_RE.finditer(init):
            assert WORK_LOOP_RANGE_PREFIX_RE.search(init[:match.start()]), (
                f"Unscoped Initialize range: {match.group()}"
            )

    def test_diary_field_labels_match_reference(self):
        text = BRAIN_SKILL.read_text(encoding=TEXT_ENCODING)
        init = text[text.index(INITIALIZE_HEADING):text.index(OTHER_MODES_HEADING)]
        reference = (BRAIN_REFS / "mempalace-workflow.md").read_text(encoding=TEXT_ENCODING)
        _, _, template = reference.partition("**Required diary entry format:**")
        template, _, _ = template.partition("**Example:**")
        assert tuple(DIARY_LABEL_RE.findall(init)) == DIARY_FIELD_LABELS
        assert tuple(DIARY_LABEL_RE.findall(template)) == DIARY_FIELD_LABELS


class TestResetSkillConfirmGuard:
    """Step 2's classifier run and Step 3c's transcript
    verification must never carry the confirmed deletion. --confirm is
    reserved for Step 5, after its dry run and the user's explicit yes."""

    def test_reset_skill_phases_do_not_attach_confirm(self):
        text = (SKILLS_DIR / "reset" / "SKILL.md").read_text(encoding=TEXT_ENCODING)
        assert "performs ONLY its own phase's work" in text, (
            "reset SKILL.md: the later-shell rule must scope each invocation "
            "to its own phase's command"
        )
        assert "never attach the confirmed deletion to a classifier or verification invocation" in text
        # The confirmed-run snippet is marked as the Step 5 confirmed run only.
        assert "Step 5's CONFIRMED run only" in text
        # The prohibition statement survives: --confirm requires dry run + yes.
        assert "Never pass `--confirm` before the user has seen the dry-run output" in text
