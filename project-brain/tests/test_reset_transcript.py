"""WP9 S-a regression tests: reset-transcript verifier (mempalace_reset wiring).

Regression-first: --verify-reset-transcript did not exist when these were
written — watched failing before implementation. The contracts come from
mempalace_reset itself (MAX_BATCH, PAGE_LIMIT, normalize_wing_for_compare).
"""

import json
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))
import mempalace_reset as mr  # noqa: E402

WING = "wiki_transcript_test"


def write_transcript(proj: Path, lines: list[dict]) -> None:
    audit = proj / ".brain" / "audit"
    audit.mkdir(parents=True, exist_ok=True)
    (audit / "reset-transcript.jsonl").write_text(
        "\n".join(json.dumps(l) for l in lines) + "\n", encoding="utf-8")


def verify(run_script, proj: Path):
    return run_script("reset_brain.py", [str(proj), "--verify-reset-transcript", WING])


def valid_transcript() -> list[dict]:
    return [
        {"tool": "mempalace_list_drawers", "wing": WING, "limit": mr.PAGE_LIMIT,
         "returned_ids": ["d1", "d2", "d3"]},
        {"tool": "mempalace_get_taxonomy", "wing": WING, "drawer_count": 3},
        {"tool": "mempalace_delete_drawers", "wing": WING, "ids": ["d1", "d2"],
         "deleted_ids": ["d1", "d2"]},
        {"tool": "mempalace_delete_drawers", "wing": WING, "ids": ["d3"],
         "deleted_ids": ["d3"]},
        {"tool": "mempalace_list_wings", "wings": ["some_other_wing"]},
    ]


class TestTranscriptVerifier:
    def test_valid_transcript_passes(self, run_script, tmp_project: Path):
        proj = tmp_project / "reset-project"
        proj.mkdir(parents=True)
        write_transcript(proj, valid_transcript())
        result = verify(run_script, proj)
        assert result.returncode == 0, result.stdout + result.stderr

    def test_single_drawer_delete_rejected(self, run_script, tmp_project: Path):
        proj = tmp_project / "reset-project"
        proj.mkdir(parents=True)
        lines = valid_transcript()
        lines.insert(2, {"tool": "mempalace_delete_drawer", "wing": WING, "id": "d9"})
        write_transcript(proj, lines)
        result = verify(run_script, proj)
        assert result.returncode == 1
        assert "single-drawer" in result.stderr

    def test_oversized_batch_rejected(self, run_script, tmp_project: Path):
        proj = tmp_project / "reset-project"
        proj.mkdir(parents=True)
        ids = [f"d{i}" for i in range(mr.MAX_BATCH + 1)]
        write_transcript(proj, [
            {"tool": "mempalace_list_drawers", "wing": WING, "limit": mr.PAGE_LIMIT,
             "returned_ids": ids},
            {"tool": "mempalace_delete_drawers", "wing": WING, "ids": ids,
             "deleted_ids": ids},
            {"tool": "mempalace_list_wings", "wings": []},
        ])
        result = verify(run_script, proj)
        assert result.returncode == 1
        assert str(mr.MAX_BATCH) in result.stderr

    def test_oversized_page_rejected(self, run_script, tmp_project: Path):
        proj = tmp_project / "reset-project"
        proj.mkdir(parents=True)
        write_transcript(proj, [
            {"tool": "mempalace_list_drawers", "wing": WING, "limit": mr.PAGE_LIMIT + 1,
             "returned_ids": ["d1"]},
            {"tool": "mempalace_delete_drawers", "wing": WING, "ids": ["d1"],
             "deleted_ids": ["d1"]},
            {"tool": "mempalace_list_wings", "wings": []},
        ])
        result = verify(run_script, proj)
        assert result.returncode == 1
        assert str(mr.PAGE_LIMIT) in result.stderr

    def test_enumerated_not_deleted_rejected(self, run_script, tmp_project: Path):
        proj = tmp_project / "reset-project"
        proj.mkdir(parents=True)
        write_transcript(proj, [
            {"tool": "mempalace_list_drawers", "wing": WING, "limit": mr.PAGE_LIMIT,
             "returned_ids": ["d1", "d2", "d3"]},
            {"tool": "mempalace_delete_drawers", "wing": WING, "ids": ["d1"],
             "deleted_ids": ["d1"]},
            {"tool": "mempalace_list_wings", "wings": []},
        ])
        result = verify(run_script, proj)
        assert result.returncode == 1
        assert "not recorded as deleted" in result.stderr

    def test_no_clearance_evidence_rejected(self, run_script, tmp_project: Path):
        proj = tmp_project / "reset-project"
        proj.mkdir(parents=True)
        lines = valid_transcript()
        # drop the final list_wings: no verification after the last delete
        write_transcript(proj, lines[:-1])
        result = verify(run_script, proj)
        assert result.returncode == 1
        assert "wing-cleared evidence" in result.stderr

    def test_wing_still_present_rejected(self, run_script, tmp_project: Path):
        proj = tmp_project / "reset-project"
        proj.mkdir(parents=True)
        write_transcript(proj, [
            {"tool": "mempalace_list_drawers", "wing": WING, "limit": mr.PAGE_LIMIT,
             "returned_ids": ["d1"]},
            {"tool": "mempalace_delete_drawers", "wing": WING, "ids": ["d1"],
             "deleted_ids": ["d1"]},
            {"tool": "mempalace_list_wings", "wings": [WING]},
        ])
        result = verify(run_script, proj)
        assert result.returncode == 1
        assert "not cleared" in result.stderr

    def test_wrong_wing_rejected(self, run_script, tmp_project: Path):
        proj = tmp_project / "reset-project"
        proj.mkdir(parents=True)
        write_transcript(proj, [
            {"tool": "mempalace_list_drawers", "wing": WING, "limit": mr.PAGE_LIMIT,
             "returned_ids": ["d1"]},
            {"tool": "mempalace_delete_drawers", "wing": "wiki_something_else",
             "ids": ["d1"], "deleted_ids": ["d1"]},
            {"tool": "mempalace_list_wings", "wings": []},
        ])
        result = verify(run_script, proj)
        assert result.returncode == 1
        assert "not recorded as deleted" in result.stderr

    def test_normalized_twin_wing_delete_not_accepted(self, run_script, tmp_project: Path):
        """A delete record for a normalized twin (same slug, different exact
        name) is another wing's record: it must not satisfy this wing's
        contract even though normalize_wing_for_compare maps both to one key."""
        proj = tmp_project / "reset-project"
        proj.mkdir(parents=True)
        assert mr.normalize_wing_for_compare("wiki-transcript-test") == mr.normalize_wing_for_compare(WING)
        write_transcript(proj, [
            {"tool": "mempalace_list_drawers", "wing": WING, "limit": mr.PAGE_LIMIT,
             "returned_ids": ["d1", "d2"]},
            {"tool": "mempalace_get_taxonomy", "wing": WING, "drawer_count": 2},
            {"tool": "mempalace_delete_drawers", "wing": "wiki-transcript-test",
             "ids": ["d1", "d2"], "deleted_ids": ["d1", "d2"]},
            {"tool": "mempalace_list_wings", "wings": []},
        ])
        result = verify(run_script, proj)
        assert result.returncode == 1
        assert "not recorded as deleted" in result.stderr

    def test_multi_wing_shared_transcript_each_wing_verifies(self, run_script, tmp_project: Path):
        """Step 3 writes every confirmed wing's calls to one transcript; the
        verifier for one wing skips the other wing's records instead of
        reporting them as violations."""
        proj = tmp_project / "reset-project"
        proj.mkdir(parents=True)
        other = "wiki_diary_other"
        lines = [
            {"tool": "mempalace_list_drawers", "wing": other, "limit": mr.PAGE_LIMIT,
             "returned_ids": ["x1"]},
            {"tool": "mempalace_get_taxonomy", "wing": other, "drawer_count": 1},
            {"tool": "mempalace_delete_drawers", "wing": other, "ids": ["x1"],
             "deleted_ids": ["x1"]},
        ] + valid_transcript()
        write_transcript(proj, lines)
        result = verify(run_script, proj)
        assert result.returncode == 0, result.stdout + result.stderr

    def test_missing_pre_delete_taxonomy_rejected(self, run_script, tmp_project: Path):
        proj = tmp_project / "reset-project"
        proj.mkdir(parents=True)
        write_transcript(proj, [
            {"tool": "mempalace_list_drawers", "wing": WING, "limit": mr.PAGE_LIMIT,
             "returned_ids": ["d1"]},
            {"tool": "mempalace_delete_drawers", "wing": WING, "ids": ["d1"],
             "deleted_ids": ["d1"]},
            {"tool": "mempalace_list_wings", "wings": []},
        ])
        result = verify(run_script, proj)
        assert result.returncode == 1
        assert "no mempalace_get_taxonomy record before the first delete" in result.stderr

    def test_taxonomy_count_mismatch_rejected(self, run_script, tmp_project: Path):
        proj = tmp_project / "reset-project"
        proj.mkdir(parents=True)
        write_transcript(proj, [
            {"tool": "mempalace_list_drawers", "wing": WING, "limit": mr.PAGE_LIMIT,
             "returned_ids": ["d1", "d2", "d3"]},
            {"tool": "mempalace_get_taxonomy", "wing": WING, "drawer_count": 2},
            {"tool": "mempalace_delete_drawers", "wing": WING, "ids": ["d1", "d2", "d3"],
             "deleted_ids": ["d1", "d2", "d3"]},
            {"tool": "mempalace_list_wings", "wings": []},
        ])
        result = verify(run_script, proj)
        assert result.returncode == 1
        assert "counts disagree" in result.stderr

    def test_missing_and_corrupt_transcript(self, run_script, tmp_project: Path):
        proj = tmp_project / "reset-project"
        proj.mkdir(parents=True)
        result = verify(run_script, proj)
        assert result.returncode == 2
        write_transcript(proj, valid_transcript())
        (proj / ".brain/audit/reset-transcript.jsonl").write_text("{not json\n", encoding="utf-8")
        result = verify(run_script, proj)
        assert result.returncode == 2
        assert "corrupt" in result.stderr

    def test_dead_benchmark_deleted(self):
        """S-a: stress_reset_benchmark.py had zero callers and is deleted (D-3)."""
        assert not (PLUGIN_ROOT / "scripts" / "stress_reset_benchmark.py").exists()
