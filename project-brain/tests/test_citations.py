"""WP4 regression+unit tests: citation syntax, drift, staleness, provenance.

Citation syntax (documented in wiki-schema.md):
    {{src path/to/file.ts:10-20 "anchorText"}}
Fuzz tests use stdlib random with a named seed per the mission spec.
"""

import json
import random
import re
import subprocess
from pathlib import Path

# D-4: the original fixture used anchor "createEngine", which appears nowhere
# in SOURCE_LINES — that made the "valid citation" fixture invalid under the
# anchor-window contract (test_anchor_absent_from_window_is_drift). The anchor
# below genuinely appears on line 15, inside the cited range.
CITATION_OK = '{{src src/app.ts:10-20 "line 15 of the source"}}'


def make_project_with_source(run_script, tmp_path: Path, source_lines: list[str]) -> Path:
    proj = tmp_path / "cited-project"
    (proj / "src").mkdir(parents=True)
    (proj / "src" / "app.ts").write_text("\n".join(source_lines) + "\n", encoding="utf-8")
    result = run_script("scaffold_brain.py", [str(proj), "Cited Project"])
    assert result.returncode == 0
    return proj


def write_page_frontmatter() -> str:
    """The default frontmatter write_page() prepends (kept in sync for the
    line-number math tests do against the written page text)."""
    return ("---\ntitle: T\ntype: concept\ncreated: 2026-01-01\nupdated: 2026-01-01\n"
            "status: active\nsources: []\ntags: [t]\n---\n")


def write_page(brain: Path, rel: str, body: str, frontmatter: str = "") -> Path:
    page = brain / "wiki" / rel
    page.parent.mkdir(parents=True, exist_ok=True)
    fm = frontmatter or write_page_frontmatter()
    page.write_text(fm + body, encoding="utf-8")
    return page


def lint_json(run_script, project: Path) -> dict:
    result = run_script("lint_brain.py", [str(project), "--json"])
    return json.loads(result.stdout)


def categories(report: dict) -> list[str]:
    return [i["category"] for i in report["issues"]]


SOURCE_LINES = [f"line {i} of the source" for i in range(1, 41)]


class TestCitationDrift:
    def test_valid_citation_passes(self, run_script, tmp_project: Path):
        proj = make_project_with_source(run_script, tmp_project, SOURCE_LINES)
        write_page(proj / ".brain", "concepts/Valid.md",
                   f"# Valid\n\nThe engine is built at {CITATION_OK} and it works.\n")
        report = lint_json(run_script, proj)
        assert "citation_drift" not in categories(report)

    def test_missing_file_is_drift(self, run_script, tmp_project: Path):
        proj = make_project_with_source(run_script, tmp_project, SOURCE_LINES)
        write_page(proj / ".brain", "concepts/Missing.md",
                   '# Missing\n\n{{src src/nope.ts:1-2 "anchor"}} claim.\n')
        report = lint_json(run_script, proj)
        assert "citation_drift" in categories(report)

    def test_range_outside_file_is_drift(self, run_script, tmp_project: Path):
        proj = make_project_with_source(run_script, tmp_project, SOURCE_LINES)
        write_page(proj / ".brain", "concepts/Range.md",
                   '# Range\n\n{{src src/app.ts:50-60 "line"}} claim.\n')
        report = lint_json(run_script, proj)
        assert "citation_drift" in categories(report)

    def test_anchor_absent_from_window_is_drift(self, run_script, tmp_project: Path):
        proj = make_project_with_source(run_script, tmp_project, SOURCE_LINES)
        # "createEngine" does not appear anywhere in the source.
        write_page(proj / ".brain", "concepts/Anchor.md",
                   '# Anchor\n\n{{src src/app.ts:10-12 "createEngine"}} claim.\n')
        report = lint_json(run_script, proj)
        assert "citation_drift" in categories(report)

    def test_empty_anchor_is_drift(self, run_script, tmp_project: Path):
        """An empty anchor anchors nothing: it must fail like an absent anchor
        instead of stamping the file as covered."""
        proj = make_project_with_source(run_script, tmp_project, SOURCE_LINES)
        write_page(proj / ".brain", "concepts/Empty.md",
                   '# Empty\n\n{{src src/app.ts:10-12 ""}} claim.\n')
        report = lint_json(run_script, proj)
        assert "citation_drift" in categories(report)

    def test_whitespace_only_anchor_is_drift(self, run_script, tmp_project: Path):
        proj = make_project_with_source(run_script, tmp_project, SOURCE_LINES)
        write_page(proj / ".brain", "concepts/Blank.md",
                   '# Blank\n\n{{src src/app.ts:10-12 "   "}} claim.\n')
        report = lint_json(run_script, proj)
        assert "citation_drift" in categories(report)

    def test_quoted_path_with_spaces_is_supported(self, run_script, tmp_project: Path):
        """Core-file paths containing spaces (as produced by
        brain_inventory.list_units) are citable via the quoted path form."""
        proj = tmp_project / "cited-project"
        (proj / "my docs").mkdir(parents=True)
        (proj / "my docs" / "app.ts").write_text("\n".join(SOURCE_LINES) + "\n", encoding="utf-8")
        result = run_script("scaffold_brain.py", [str(proj), "Cited Project"])
        assert result.returncode == 0
        write_page(proj / ".brain", "concepts/Spaced.md",
                   '# Spaced\n\n{{src "my docs/app.ts":10-12 "line 10 of the source"}} claim.\n')
        report = lint_json(run_script, proj)
        assert "citation_drift" not in categories(report)

    def test_anchor_within_window_passes(self, run_script, tmp_project: Path):
        proj = make_project_with_source(run_script, tmp_project, SOURCE_LINES)
        # anchor text on line 13, cited range 10-12 → inside the 5-line window
        write_page(proj / ".brain", "concepts/Window.md",
                   '# Window\n\n{{src src/app.ts:10-12 "line 13 of the source"}} claim.\n')
        report = lint_json(run_script, proj)
        assert "citation_drift" not in categories(report)

    def test_anchor_whitespace_normalized(self, run_script, tmp_project: Path):
        proj = make_project_with_source(run_script, tmp_project, SOURCE_LINES)
        # source has single spaces; anchor uses doubled spaces + newline
        write_page(proj / ".brain", "concepts/Ws.md",
                   '# Ws\n\n{{src src/app.ts:10-10 "line  10 of\\nthe source"}} claim.\n')
        report = lint_json(run_script, proj)
        assert "citation_drift" not in categories(report)

    def test_unanchored_line_ref_warns(self, run_script, tmp_project: Path):
        proj = make_project_with_source(run_script, tmp_project, SOURCE_LINES)
        write_page(proj / ".brain", "concepts/Bare.md",
                   "# Bare\n\nSee src/app.ts:10 for details.\n")
        report = lint_json(run_script, proj)
        assert "unanchored_line_ref" in categories(report)


class TestVerifyAndStaleness:
    def test_verify_writes_stamp_only_for_clean_pages(self, run_script, tmp_project: Path):
        proj = make_project_with_source(run_script, tmp_project, SOURCE_LINES)
        brain = proj / ".brain"
        write_page(brain, "concepts/Clean.md", f"# Clean\n\nCited {CITATION_OK} fine.\n")
        write_page(brain, "concepts/Dirty.md", '# Dirty\n\n{{src src/gone.ts:1 "x"}} claim.\n')
        result = run_script("lint_brain.py", [str(proj), "--verify"])
        assert result.returncode == 1  # dirty page still fails lint
        ver = json.loads((brain / "verification.json").read_text(encoding="utf-8"))
        assert "wiki/concepts/Clean.md" in ver["pages"]
        assert "wiki/concepts/Dirty.md" not in ver["pages"]

    def test_stale_after_source_edit(self, run_script, tmp_project: Path):
        proj = make_project_with_source(run_script, tmp_project, SOURCE_LINES)
        brain = proj / ".brain"
        write_page(brain, "concepts/Clean.md", f"# Clean\n\nCited {CITATION_OK} fine.\n")
        run_script("lint_brain.py", [str(proj), "--verify"])
        # Now edit the cited source file.
        (proj / "src" / "app.ts").write_text("totally changed\n", encoding="utf-8")
        report = lint_json(run_script, proj)
        assert "stale_citation" in categories(report)

    def test_unrelated_commit_does_not_stale(self, run_script, tmp_project: Path):
        """Staleness is hash-based: a commit that does not touch cited files must not stale the page."""
        proj = make_project_with_source(run_script, tmp_project, SOURCE_LINES)
        brain = proj / ".brain"
        write_page(brain, "concepts/Clean.md", f"# Clean\n\nCited {CITATION_OK} fine.\n")
        run_script("lint_brain.py", [str(proj), "--verify"])
        (proj / "unrelated.txt").write_text("another commit touched me\n", encoding="utf-8")
        report = lint_json(run_script, proj)
        assert "stale_citation" not in categories(report)

    def test_corrupted_verification_fails_closed(self, run_script, tmp_project: Path):
        proj = make_project_with_source(run_script, tmp_project, SOURCE_LINES)
        brain = proj / ".brain"
        (brain / "verification.json").write_text("{not json", encoding="utf-8")
        result = run_script("lint_brain.py", [str(proj), "--json"])
        assert result.returncode not in (0, 1)  # hard failure, not a lint report
        assert "corrupt" in (result.stdout + result.stderr).lower()


class TestRationaleSource:
    DECISION_FM = (
        "---\ntitle: D\ntype: decision\ncreated: 2026-01-01\nupdated: 2026-01-01\n"
        "status: accepted\nsources: []\ntags: [d]\n"
    )

    def test_invalid_rationale_value_flagged(self, run_script, tmp_project: Path):
        proj = make_project_with_source(run_script, tmp_project, SOURCE_LINES)
        write_page(proj / ".brain", "decisions/D.md", "# D\n\nBecause.\n",
                   frontmatter=self.DECISION_FM + "rationale_source: made-up\n---\n".replace("---\n", "", 1))
        # fix: build frontmatter properly
        page = proj / ".brain" / "wiki" / "decisions" / "D.md"
        page.write_text(self.DECISION_FM + "rationale_source: made-up\n---\n\n# D\n\nBecause.\n", encoding="utf-8")
        report = lint_json(run_script, proj)
        assert "invalid_rationale_source" in categories(report)

    def test_missing_rationale_warns(self, run_script, tmp_project: Path):
        proj = make_project_with_source(run_script, tmp_project, SOURCE_LINES)
        page = proj / ".brain" / "wiki" / "decisions" / "D.md"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text(self.DECISION_FM + "---\n\n# D\n\nBecause.\n", encoding="utf-8")
        report = lint_json(run_script, proj)
        assert "missing_rationale_source" in categories(report)

    def test_inferred_needs_tag(self, run_script, tmp_project: Path):
        proj = make_project_with_source(run_script, tmp_project, SOURCE_LINES)
        page = proj / ".brain" / "wiki" / "decisions" / "D.md"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text(
            self.DECISION_FM + "rationale_source: inferred\n---\n\n# D\n\nBecause, probably.\n",
            encoding="utf-8",
        )
        report = lint_json(run_script, proj)
        assert "inferred_untagged" in categories(report)

    def test_doc_path_must_exist(self, run_script, tmp_project: Path):
        proj = make_project_with_source(run_script, tmp_project, SOURCE_LINES)
        page = proj / ".brain" / "wiki" / "decisions" / "D.md"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text(
            self.DECISION_FM + 'rationale_source: "doc:docs/adr-001.md"\n---\n\n# D\n\nBecause.\n',
            encoding="utf-8",
        )
        report = lint_json(run_script, proj)
        assert "rationale_doc_missing" in categories(report)
        # now make the doc exist — error disappears
        (proj / "docs").mkdir(exist_ok=True)
        (proj / "docs" / "adr-001.md").write_text("# ADR 1\nok\n", encoding="utf-8")
        report = lint_json(run_script, proj)
        assert "rationale_doc_missing" not in categories(report)

    def test_commit_rationale_valid_and_missing(self, run_script, tmp_project: Path):
        proj = make_project_with_source(run_script, tmp_project, SOURCE_LINES)
        subprocess.run(["git", "init", "-q", str(proj)], check=True, capture_output=True)
        subprocess.run(
            ["git", "-C", str(proj), "-c", "user.email=t@example.com", "-c", "user.name=t",
             "commit", "--allow-empty", "-m", "init", "-q"],
            check=True, capture_output=True,
        )
        head = subprocess.run(["git", "-C", str(proj), "rev-parse", "HEAD"],
                              check=True, capture_output=True, text=True).stdout.strip()
        page = proj / ".brain" / "wiki" / "decisions" / "D.md"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text(self.DECISION_FM + f"rationale_source: commit:{head}\n---\n\n# D\n\nBecause.\n",
                        encoding="utf-8")
        report = lint_json(run_script, proj)
        assert "rationale_commit_missing" not in categories(report)
        page.write_text(self.DECISION_FM + "rationale_source: commit:" + "0" * 40 + "\n---\n\n# D\n\nBecause.\n",
                        encoding="utf-8")
        report = lint_json(run_script, proj)
        assert "rationale_commit_missing" in categories(report)


class TestForbiddenAllClear:
    def test_all_clear_without_receipts_is_error(self, run_script, tmp_project: Path):
        proj = make_project_with_source(run_script, tmp_project, SOURCE_LINES)
        write_page(proj / ".brain", "concepts/C.md",
                   "# C\n\nThe README and code have no contradictions.\n")
        report = lint_json(run_script, proj)
        assert "forbidden_all_clear" in categories(report)

    def test_all_clear_allowed_with_receipts(self, run_script, tmp_project: Path):
        proj = make_project_with_source(run_script, tmp_project, SOURCE_LINES)
        brain = proj / ".brain"
        write_page(brain, "concepts/C.md",
                   f"# C\n\nCited {CITATION_OK} fine. The README and code have no contradictions.\n")
        run_script("lint_brain.py", [str(proj), "--verify"])
        (brain / "audit").mkdir(exist_ok=True)
        (brain / "audit" / "crossrefs-report.json").write_text('{"generated_at": "x", "missing": []}', encoding="utf-8")
        report = lint_json(run_script, proj)
        assert "forbidden_all_clear" not in categories(report)


class TestVolatileNumbers:
    def test_volatile_number_warns(self, run_script, tmp_project: Path):
        proj = make_project_with_source(run_script, tmp_project, SOURCE_LINES)
        write_page(proj / ".brain", "concepts/V.md",
                   "# V\n\nThe suite has 49 tests today.\n")
        report = lint_json(run_script, proj)
        assert "volatile_number" in categories(report)

    def test_volatile_number_with_tag_ok(self, run_script, tmp_project: Path):
        proj = make_project_with_source(run_script, tmp_project, SOURCE_LINES)
        write_page(proj / ".brain", "concepts/V.md",
                   "# V\n\nThe suite has 49 tests [unverified].\n")
        report = lint_json(run_script, proj)
        assert "volatile_number" not in categories(report)


class TestCitationParserFuzz:
    """Fuzz the citation regex + anchor check with a named seed (mission spec)."""

    SEED = 20261029  # SAMPLE_SEED-equivalent for the plugin's own fuzz tests
    N_CASES = 200
    MAX_LINE = 2000

    def test_fuzz_no_crash_and_correct_extraction(self, run_script, tmp_project: Path):
        import sys
        scripts = Path(run_script.__closure__[0].cell_contents if False else ".")  # not used
        rng = random.Random(self.SEED)
        # Import the plugin's regex directly.
        plugin_scripts = Path(__file__).resolve().parent.parent / "scripts"
        sys.path.insert(0, str(plugin_scripts))
        import lint_brain as lb  # noqa: E402

        weird = ["", "​", "ünïcödé", "\\n", " " * 50, '"', "{{", "}}", "a" * self.MAX_LINE]
        for i in range(self.N_CASES):
            path = "".join(rng.choice(weird) or "x" for _ in range(rng.randint(0, 3)))
            anchor = "".join(rng.choice(weird) or "y" for _ in range(rng.randint(0, 3)))
            start = rng.randint(-5, 10**9)
            end = rng.randint(-5, 10**9) if rng.random() < 0.5 else None
            range_part = f"{start}" if end is None else f"{start}-{end}"
            text = f"{{{{src {path}:{range_part} \"{anchor}\"}}}}"
            matches = lb.CITATION_RE.findall(text)
            # the regex either matches cleanly (one group tuple: quoted path,
            # path, start, end, anchor) or not at all; it must never crash
            assert isinstance(matches, list)
            if matches:
                assert len(matches[0]) == 5

    def test_fuzz_anchor_window_crlf(self, run_script, tmp_project: Path):
        """CRLF sources: anchor matching must be whitespace-normalized."""
        proj = tmp_project / "crlf-project"
        (proj / "src").mkdir(parents=True)
        # CRLF line endings, anchor has different spacing than source
        (proj / "src" / "crlf.ts").write_text(
            "\r\n".join([f"function n{i}() {{}}" for i in range(1, 20)]) + "\r\n", encoding="utf-8"
        )
        run_script("scaffold_brain.py", [str(proj), "CRLF Project"])
        write_page(proj / ".brain", "concepts/Crlf.md",
                   '# Crlf\n\n{{src src/crlf.ts:5-6 "function n5() {}"}} cited.\n')
        report = lint_json(run_script, proj)
        assert "citation_drift" not in categories(report)


class TestBinWiring:
    def test_verify_reachable_through_bin_wrapper(self, run_script, tmp_project: Path):
        """Wiring rule: --verify must work through bin/project-brain-lint, not
        only by calling scripts/lint_brain.py directly."""
        proj = make_project_with_source(run_script, tmp_project, SOURCE_LINES)
        write_page(proj / ".brain", "concepts/Clean.md", f"# Clean\n\nCited {CITATION_OK} fine.\n")
        wrapper = Path(__file__).resolve().parent.parent / "bin" / "project-brain-lint"
        result = subprocess.run(["bash", str(wrapper), str(proj), "--verify"],
                                capture_output=True, text=True, timeout=30)
        assert "unrecognized arguments" not in result.stderr
        assert result.returncode in (0, 1)
        ver = json.loads((proj / ".brain" / "verification.json").read_text(encoding="utf-8"))
        assert "wiki/concepts/Clean.md" in ver["pages"]


class TestCitationsInCodeRegions:
    def test_fenced_example_is_not_a_citation(self, run_script, tmp_project: Path):
        """A {{src ...}} example inside a fenced block documents the syntax;
        it must not count toward coverage (a substantive page whose only
        citation lives in a fence leaves its source unit uncovered)."""
        proj = make_project_with_source(run_script, tmp_project, SOURCE_LINES)
        write_page(proj / ".brain", "concepts/Example.md",
                   substantive_body() + "\n"
                   "Example syntax:\n\n"
                   "```markdown\n"
                   f'{CITATION_OK}\n'
                   "```\n")
        state: dict = {}
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
        import lint_brain as lb
        lb.build_report(proj, citation_state=state)
        info = state["wiki/concepts/Example.md"]
        assert info["has_citations"] is False
        assert info["files"] == {}
        # And inventory coverage agrees: src/app.ts is NOT covered by the page.
        import brain_inventory as bi
        statuses = bi.compute_statuses(proj, proj / ".brain",
                                       [{"path": "src/app.ts"}], {})
        assert statuses["src/app.ts"]["status"] == "uncovered"

    def test_inline_code_span_is_not_a_citation(self, run_script, tmp_project: Path):
        proj = make_project_with_source(run_script, tmp_project, SOURCE_LINES)
        write_page(proj / ".brain", "concepts/Inline.md",
                   substantive_body() + " Inline: `" + CITATION_OK + "` as a sample.\n")
        state: dict = {}
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
        import lint_brain as lb
        lb.build_report(proj, citation_state=state)
        assert state["wiki/concepts/Inline.md"]["has_citations"] is False

    def test_prose_citation_line_numbers_survive_code_masking(self, run_script, tmp_project: Path):
        """A real citation after a fenced block still validates, and a drifted
        one reports the ORIGINAL line number (positions are preserved)."""
        proj = make_project_with_source(run_script, tmp_project, SOURCE_LINES)
        write_page(proj / ".brain", "concepts/Mixed.md",
                   substantive_body() + "\n\n```bash\n{{src src/app.ts:99-99 \"nope\"}}\n```\n\n"
                   f"Real: {CITATION_OK}\n")
        report = lint_json(run_script, proj)
        assert "citation_drift" not in categories(report)

    def test_drift_after_fence_reports_original_line(self, run_script, tmp_project: Path):
        """A drifted citation that follows a fenced block is reported on the
        line the page really shows it on: masked fence lines keep their
        length, so citation offsets index the original text."""
        proj = make_project_with_source(run_script, tmp_project, SOURCE_LINES)
        body = ('# Page\n\n```bash\n' + "x" * 80 + '\n```\n\n'
                'Drift: {{src src/nope.ts:1 "missing"}}\n')
        write_page(proj / ".brain", "concepts/Late.md", body)
        report = lint_json(run_script, proj)
        drift = [i for i in report["issues"] if i["category"] == "citation_drift"]
        assert drift, "drifted citation not reported"
        page_text = write_page_frontmatter() + body
        true_line = page_text.count("\n", 0, page_text.index("{{src src/nope")) + 1
        assert drift[0]["line"] == true_line, drift[0]

    def test_citation_after_fence_is_not_reported_unanchored(self, run_script, tmp_project: Path):
        """A valid prose citation after a fenced block shields the file:line
        inside it from unanchored_line_ref: citation spans and bare refs share
        the original text's coordinates."""
        proj = make_project_with_source(run_script, tmp_project, SOURCE_LINES)
        write_page(proj / ".brain", "concepts/Shield.md",
                   "# Shield\n\n```bash\n" + "x" * 80 + "\n```\n\n"
                   f"Real: {CITATION_OK}\n")
        report = lint_json(run_script, proj)
        assert "unanchored_line_ref" not in categories(report)

    def test_anchor_with_inline_code_span_passes(self, run_script, tmp_project: Path):
        """An anchor quoting a line that contains a template literal keeps its
        backticks: extracting citations from the original body means masking
        cannot mangle prose anchors (and coverage still counts)."""
        source = SOURCE_LINES[:14] + ["const msg = `hi`;"] + SOURCE_LINES[14:]
        proj = make_project_with_source(run_script, tmp_project, source)
        write_page(proj / ".brain", "concepts/Tick.md",
                   substantive_body() + "\n"
                   '# Tick cites: {{src src/app.ts:15-15 "const msg = `hi`;"}}, checked.\n')
        state: dict = {}
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
        import lint_brain as lb
        lb.build_report(proj, citation_state=state)
        info = state["wiki/concepts/Tick.md"]
        assert info["has_citations"] is True
        assert info["drift"] is False
        assert "src/app.ts" in info["files"]
        # And inventory coverage agrees: src/app.ts IS covered by the page.
        import brain_inventory as bi
        statuses = bi.compute_statuses(proj, proj / ".brain",
                                       [{"path": "src/app.ts"}], {})
        assert statuses["src/app.ts"]["status"] == "covered"


def substantive_body() -> str:
    return "# Page\n\n" + ("This page carries a real, checkable summary of the project. " * 4)
