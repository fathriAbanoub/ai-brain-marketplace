"""KD-19 regression tests: the brain skill must teach context discipline.

Found live in Part 2 iter-2: with a ~100K-token gateway limit the inner
model (a) ran the graph generator three times in one session, (b) read whole
large files (one 78K-char read directly preceded the fatal request), and
(c) treated the operating loop as single-session-or-bust, never writing a
page before the context died. All three failure modes are addressable by
skill text; these tests pin that text.
"""

from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
BRAIN_SKILL = PLUGIN_ROOT / "skills" / "brain" / "SKILL.md"


@pytest.fixture(scope="module")
def skill_text() -> str:
    return BRAIN_SKILL.read_text(encoding="utf-8")


class TestBoundedReads:
    def test_slice_guidance_present(self, skill_text: str):
        assert "bounded slice" in skill_text, (
            "brain/SKILL.md must tell the model to read source files in "
            "bounded slices (whole-file reads of large sources exhaust the "
            "context window — observed live: a 78K-char read preceded the "
            "fatal prompt-exceeds-max-length request)"
        )

    def test_slice_example_uses_sed_or_limit(self, skill_text: str):
        assert ("sed -n" in skill_text) or ("limit" in skill_text.lower()), (
            "the bounded-read guidance must name a concrete mechanism "
            "(sed -n 'A,Bp' or a Read limit)"
        )


class TestSingleGraphRun:
    def test_at_most_once_rule_present(self, skill_text: str):
        assert "at most once" in skill_text, (
            "brain/SKILL.md must cap graph generation at one run per session "
            "(observed live: three consecutive graph-generator invocations in "
            "one session, wasting context on duplicate output)"
        )


class TestBatchAndPersist:
    def test_batch_guidance_present(self, skill_text: str):
        assert "small batch" in skill_text, (
            "brain/SKILL.md must instruct covering units in small batches "
            "with lint between batches — the inventory persists progress, so "
            "ending a session and continuing in the next one is the designed "
            "path under a tight context budget"
        )

    def test_inventory_persistence_stated(self, skill_text: str):
        assert "persists progress" in skill_text, (
            "the batching guidance must say WHY it is safe: the inventory "
            "file on disk is the resume surface"
        )
