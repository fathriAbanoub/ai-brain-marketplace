"""WP5: regression fixtures from the observed failure session.

Five lint-failure shapes an agent actually produced (synthetic minimal
reconstructions — same shapes, no project code, no home paths):

1. flow-style `sources: [{ path: ..., reliability: ... }]` objects
2. hybrid markdown-wikilink citations `[[README.md](../../README.md)]` and
   bare `file.ext:line` references
3. wikilinks to a page that does not exist and to a non-wiki file
4. a page listed twice in index.md, plus index entries pointing at no page
5. a `{{src file:A-B "anchor"}}` whose anchor was copied from a README and no
   longer exists at the cited lines

For each: a test asserting the category fires AND its message carries the
exact documented fix, plus one convergence test that applies the documented
fixes (--reindex, plain `sources:` strings, re-citing via `grep -n`) and
reaches zero errors.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
LINT = PLUGIN_ROOT / "scripts" / "lint_brain.py"


def run_lint(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(LINT), str(root), *args],
                          capture_output=True, text=True, timeout=60)


def lint_issues(root: Path) -> list[dict]:
    r = run_lint(root, "--json")
    assert r.returncode in (0, 1), r.stderr
    return json.loads(r.stdout)["issues"]


def categories(issues: list[dict]) -> set[str]:
    return {i["category"] for i in issues}


def one(issues: list[dict], category: str) -> dict:
    matches = [i for i in issues if i["category"] == category]
    assert matches, f"expected {category} in {[i['category'] for i in issues]}"
    return matches[0]


@pytest.fixture
def project(run_script, tmp_path: Path) -> Path:
    root = tmp_path / "regression-project"
    root.mkdir()
    result = run_script("scaffold_brain.py", [str(root), "Regression"])
    assert result.returncode == 0, result.stderr
    # A real README at the project root — the careless agent cites it.
    (root / "README.md").write_text(
        "# Demo project\n\nThe engine boots in order: kernel, then audio graph.\n"
        "Sample rate is fixed at 48 kHz.\n",
        encoding="utf-8")
    (root / "engine.py").write_text("RATE = 48000\n", encoding="utf-8")
    return root


PAGE_FM = ("---\ntitle: {title}\ntype: concept\ncreated: 2026-01-01\n"
           "updated: 2026-01-01\nstatus: active\n{sources}tags: [t]\n---\n")


def write_page(root: Path, rel: str, body: str, sources: str = "sources: []\n") -> Path:
    page = root / ".brain" / "wiki" / rel
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(PAGE_FM.format(title=page.stem, sources=sources) + "\n" + body,
                    encoding="utf-8")
    return page


def substantive(body: str) -> str:
    """Pad the body past the short-page warn so scenario tests see only the
    failure class under test."""
    filler = ("This page carries a real, checkable summary of the project "
              "for the scenario under test. ")
    return filler * 4 + body


# --- scenario 1: flow-style sources objects -------------------------------------

class TestSourcesObjectEntry:
    def test_category_and_fix_in_message(self, project: Path):
        write_page(project, "concepts/Bad.md", substantive("Claim.\n"),
                   sources="sources: [{ path: README.md, reliability: primary }]\n")
        issue = one(lint_issues(project), "invalid_sources_entry")
        assert "plain root-relative path strings" in issue["message"]
        assert "reliability belongs only in the frontmatter of wiki/sources/* pages" in issue["message"]


# --- scenario 2: hybrid citations and bare file:line refs ------------------------

class TestHybridAndBareRefs:
    def test_hybrid_wikilink_is_a_broken_wikilink(self, project: Path):
        write_page(project, "concepts/Hybrid.md",
                   substantive("Details: [[README.md](../../README.md)].\n"))
        issue = one(lint_issues(project), "broken_wikilink")
        assert "hybrid markdown-wikilink" in issue["message"]
        # README.md is a real repo file outside the wiki: the fix is the
        # code-span path form.
        assert "non-wiki files are referenced as a code-span path" in issue["message"]

    def test_bare_file_line_ref_warns_with_the_citation_fix(self, project: Path):
        write_page(project, "concepts/Bare.md",
                   substantive("The rate is defined at engine.py:1.\n"))
        issue = one(lint_issues(project), "unanchored_line_ref")
        assert '{{src engine.py:1 "anchorText"}}' in issue["message"]


# --- scenario 3: wikilinks to missing pages and non-wiki files -------------------

class TestNonWikiAndMissingTargets:
    def test_non_wiki_file_link_carries_code_span_fix(self, project: Path):
        report = project / "graphify-out" / "GRAPH_REPORT.md"
        report.parent.mkdir(exist_ok=True)
        report.write_text("# report\n", encoding="utf-8")
        write_page(project, "concepts/Graph.md",
                   substantive("See [[graphify-out/GRAPH_REPORT.md]].\n"))
        issue = one(lint_issues(project), "broken_wikilink")
        assert "non-wiki files are referenced as a code-span path" in issue["message"]
        assert "`graphify-out/GRAPH_REPORT.md`" in issue["message"]

    def test_missing_page_link_carries_create_or_fix(self, project: Path):
        write_page(project, "concepts/Linker.md",
                   substantive("Related: [[Ghost Topic]].\n"))
        issue = one(lint_issues(project), "broken_wikilink")
        assert "create the target page or fix the link" in issue["message"]


# --- scenario 4: hand-edited index (duplicates and ghosts) ------------------------

class TestIndexInvariants:
    def test_duplicate_and_ghost_entries_carry_reindex_fix(self, project: Path):
        write_page(project, "concepts/Twice.md", substantive("Listed twice.\n"))
        index = project / ".brain" / "wiki" / "index.md"
        index.write_text(
            "# Project Brain Index - Regression\n\n## Concepts\n\n"
            "- [[concepts/Twice]] — listed twice below\n"
            "- [[concepts/Twice]] — duplicate entry\n"
            "- [[Ghost Page]] — points at no page\n",
            encoding="utf-8")
        issues = lint_issues(project)
        dup = one(issues, "duplicate_index_entry")
        assert "--reindex" in dup["message"]
        ghost = one(issues, "index_entry_target_missing")
        assert "--reindex" in ghost["message"]


# --- scenario 5: citation anchor drift --------------------------------------------

class TestCitationDrift:
    def test_copied_anchor_reports_drift_with_grep_fix(self, project: Path):
        # The anchor was copied from a template README; the cited lines of the
        # real README say something else.
        write_page(project, "concepts/Drift.md",
                   substantive('The engine boots {{src README.md:1-2 "Usage: install and run"}}.\n'))
        issue = one(lint_issues(project), "citation_drift")
        assert 'grep -n "Usage: install and run" README.md' in issue["message"]
        assert "re-cite the range they actually appear in" in issue["message"]

    def test_range_outside_file_also_reports_drift(self, project: Path):
        write_page(project, "concepts/Drift2.md",
                   substantive('Rate claim {{src README.md:40-99 "Sample rate"}}.\n'))
        issue = one(lint_issues(project), "citation_drift")
        assert "outside README.md" in issue["message"]


# --- convergence: apply the documented fixes, reach zero errors -------------------

class TestConvergenceToZeroErrors:
    def test_documented_fixes_reach_zero_errors(self, project: Path):
        """The careless brain from the observed session, repaired exactly the
        way the fix hints say: plain sources strings, code-span path for the
        non-wiki file, a real page for the missing target, --reindex for the
        hand-edited index, and re-cited lines found with grep -n."""
        graph_report = project / "graphify-out" / "GRAPH_REPORT.md"
        graph_report.parent.mkdir(exist_ok=True)
        graph_report.write_text("# report\n", encoding="utf-8")

        # 1. flow-style sources object
        write_page(project, "concepts/Bad.md",
                   substantive("Claim about the README: `README.md`.\n"),
                   sources="sources: [{ path: README.md, reliability: primary }]\n")
        # 2. hybrid citation + bare file:line ref
        write_page(project, "concepts/Hybrid.md",
                   substantive("Details: [[README.md](../../README.md)]; rate at engine.py:1.\n"))
        # 3. missing page + non-wiki file wikilink
        write_page(project, "concepts/Graph.md",
                   substantive("See [[graphify-out/GRAPH_REPORT.md]] and [[Ghost Topic]].\n"))
        # 4. hand-edited index
        (project / ".brain" / "wiki" / "index.md").write_text(
            "# Project Brain Index - Regression\n\n## Concepts\n\n"
            "- [[concepts/Bad]] — once\n- [[concepts/Bad]] — twice\n- [[Ghost Page]]\n",
            encoding="utf-8")
        # 5. drifted citation
        write_page(project, "concepts/Drift.md",
                   substantive('Boots {{src README.md:1-2 "Usage: install and run"}}.\n'))

        issues = lint_issues(project)
        assert categories(issues) >= {
            "invalid_sources_entry", "broken_wikilink", "duplicate_index_entry",
            "index_entry_target_missing", "citation_drift",
        }
        assert [i for i in issues if i["severity"] == "error"]

        # --- repairs, exactly as the printed hints describe ---
        # (1) plain root-relative path strings
        write_page(project, "concepts/Bad.md",
                   substantive("Claim about the README: `README.md`.\n"),
                   sources="sources: [README.md]\n")
        # (2) hybrid link -> code-span path for the repo file (the hint's
        #     fix); bare ref -> verified citation (grep -n "RATE" engine.py
        #     finds line 1)
        write_page(project, "concepts/Hybrid.md",
                   substantive("Details: `README.md`; the rate {{src engine.py:1 \"RATE = 48000\"}}.\n"))
        # (3) code-span path for the non-wiki file; a real page for the target
        write_page(project, "concepts/Graph.md",
                   substantive("See `graphify-out/GRAPH_REPORT.md` and [[Ghost Topic]].\n"))
        write_page(project, "concepts/Ghost Topic.md", substantive("Now it exists.\n"))
        # (5) re-cite the lines grep -n actually found in README.md
        write_page(project, "concepts/Drift.md",
                   substantive('The engine boots {{src README.md:2-2 "The engine boots in order"}}.\n'))
        # (4) regenerate the index with the script (never by hand)
        result = run_lint(project, "--reindex")
        assert result.returncode in (0, 1)
        assert "reindexed" in result.stdout

        issues_after = lint_issues(project)
        errors = [i for i in issues_after if i["severity"] == "error"]
        assert errors == [], json.dumps(errors, indent=2)
