"""Tests for wing classification (round 2): classify_wings in
scripts/mempalace_reset.py and the --classify-wings CLI in reset_brain.py.

Scenarios come from the live-run incident (a directory-derived wing listed as
an "orphan", a foreign diary wing treated as the brain's, names normalized
three different ways by hand) and from the brief's regression list: the rules
the prose got wrong are now pinned as executable behavior.
"""

from __future__ import annotations

import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PLUGIN_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))

import mempalace_reset as mr  # noqa: E402
import reset_brain  # noqa: E402
from scaffold_brain import generate_wiki_wing_name  # noqa: E402

PROJECT_DIR = "demo_app"
RECORDED_WING = "wiki_demo_app_20261030T043956Z"
RECORDED_AGENT = "brain_demo_app"


def classify(wings, recorded_wing=RECORDED_WING, agent=RECORDED_AGENT, project_dir=PROJECT_DIR):
    return mr.classify_wings(wings, recorded_wing, agent, project_dir)


def row_by_name(classification, name):
    return next(r for r in classification.rows if r.wing == name)


# --- fixtures -----------------------------------------------------------------


def incident_wings():
    """The live-run palace: the recorded wiki wing was never mined, so the
    palace holds only non-brain wings (plus another project's wing)."""
    return {
        "demo_app": 1309,                        # directory-derived session transcripts
        "wing_demo_app": 8,                      # diary of a different agent (checkpoint hook)
        "sessions": 412,
        "wing_sessions": 57,
        "-home-user-work-demo-app": 64,          # harness path-style wing
        "wiki_other_proj_20261020T110000Z": 12,  # another project's wiki wing
    }


# --- the incident ---------------------------------------------------------------


def test_incident_classification():
    classification = classify(incident_wings())
    assert row_by_name(classification, "demo_app").wing_class == mr.CLASS_DIRECTORY_DERIVED
    assert row_by_name(classification, "wing_demo_app").wing_class == mr.CLASS_OTHER_DIARY
    assert row_by_name(classification, "sessions").wing_class == mr.CLASS_SESSION_OR_PATH
    assert row_by_name(classification, "wing_sessions").wing_class == mr.CLASS_SESSION_OR_PATH
    assert row_by_name(classification, "-home-user-work-demo-app").wing_class == mr.CLASS_SESSION_OR_PATH
    assert row_by_name(classification, "wiki_other_proj_20261020T110000Z").wing_class == mr.CLASS_OTHER
    assert not any(r.wing_class == mr.CLASS_ORPHAN_CANDIDATE for r in classification.rows)
    assert classification.outcome == mr.OUTCOME_C


def test_wing_slug_is_never_the_brain_diary():
    """False-match regression: wing_<slug> must not classify as the brain
    diary when the recorded agent is brain_<slug> — the diary wing is
    wing_<recorded agent>, not wing_<project slug>."""
    classification = classify({"wing_demo_app": 8})
    row = row_by_name(classification, "wing_demo_app")
    assert row.wing_class == mr.CLASS_OTHER_DIARY
    assert row.wing_class != mr.CLASS_BRAIN_DIARY


# --- normalization ---------------------------------------------------------------


def test_recorded_wing_matches_through_normalization():
    classification = classify(
        {"wiki_demo_app_20261030t043956z": 21},
        recorded_wing="wiki_Demo_App_20261030T043956Z",
    )
    assert row_by_name(classification, "wiki_demo_app_20261030t043956z").wing_class == mr.CLASS_BRAIN_WIKI
    assert classification.outcome == mr.OUTCOME_A


def test_legacy_hyphenated_forms_normalize_together():
    classification = classify({"wiki-demo-app": 6}, recorded_wing="wiki_demo_app")
    assert row_by_name(classification, "wiki-demo-app").wing_class == mr.CLASS_BRAIN_WIKI


def test_diary_wing_matches_through_normalization():
    classification = classify({"wing_brain-demo-app": 4}, agent="Brain Demo App")
    assert row_by_name(classification, "wing_brain-demo-app").wing_class == mr.CLASS_BRAIN_DIARY


# --- collisions -------------------------------------------------------------------


def test_collision_keeps_and_flags_all_rows():
    classification = classify({"wiki-demo-app": 5, "wiki_demo_app": 7})
    assert len(classification.rows) == 2  # none collapsed
    twins = [r for r in classification.rows if r.normalized == "wiki_demo_app"]
    assert {r.wing for r in twins} == {"wiki-demo-app", "wiki_demo_app"}
    assert all(mr.FLAG_COLLISION in r.flags for r in twins)


def test_brain_wing_collision_flags_but_keeps_outcome():
    classification = classify(
        {"wiki-demo-app": 5, "wiki_demo_app": 7}, recorded_wing="wiki_demo_app"
    )
    for name in ("wiki-demo-app", "wiki_demo_app"):
        row = row_by_name(classification, name)
        assert row.wing_class == mr.CLASS_BRAIN_WIKI
        assert mr.FLAG_COLLISION in row.flags
    assert classification.outcome == mr.OUTCOME_A  # flag forces a question, not a letter change


# --- orphan scan --------------------------------------------------------------------


def test_orphan_scan_finds_wiki_family_when_recorded_absent():
    classification = classify({"wiki_demo_app_20261026t164600z": 3, "demo_app": 1309})
    assert row_by_name(classification, "wiki_demo_app_20261026t164600z").wing_class == mr.CLASS_ORPHAN_CANDIDATE
    assert row_by_name(classification, "demo_app").wing_class == mr.CLASS_DIRECTORY_DERIVED
    assert classification.outcome == mr.OUTCOME_B


def test_bare_directory_wing_is_never_an_orphan():
    classification = classify({"demo_app": 9}, recorded_wing=None, agent=None)
    assert row_by_name(classification, "demo_app").wing_class == mr.CLASS_DIRECTORY_DERIVED
    assert classification.outcome == mr.OUTCOME_C


def test_orphan_scan_matches_higher_precision_and_suffix_forms():
    classification = classify(
        {
            "wiki_demo_app_20261026t164600123456z": 2,  # microsecond form
            "wiki_demo_app_20261026t164600z_2": 1,      # numeric collision suffix
        }
    )
    assert {r.wing_class for r in classification.rows} == {mr.CLASS_ORPHAN_CANDIDATE}
    assert classification.outcome == mr.OUTCOME_B


def test_other_projects_wiki_wing_is_not_an_orphan():
    classification = classify({"wiki_other_proj_20261020T110000Z": 12})
    assert row_by_name(classification, "wiki_other_proj_20261020T110000Z").wing_class == mr.CLASS_OTHER
    assert classification.outcome == mr.OUTCOME_C


def test_orphan_slug_prefers_recorded_wing_over_directory_name():
    """The slug comes from the recorded wiki wing when present, even when the
    directory name differs."""
    classification = classify(
        {"wiki_demo_app_20261026t164600z": 3},
        recorded_wing=RECORDED_WING,
        agent=None,
        project_dir="some_other_dir",
    )
    assert classification.orphan_slug == "demo_app"
    assert classification.outcome == mr.OUTCOME_B


# --- outcomes ------------------------------------------------------------------------


def test_outcome_a_when_recorded_wings_present():
    classification = classify({RECORDED_WING: 21, "wing_brain_demo_app": 4, "demo_app": 1309})
    assert row_by_name(classification, RECORDED_WING).wing_class == mr.CLASS_BRAIN_WIKI
    assert row_by_name(classification, "wing_brain_demo_app").wing_class == mr.CLASS_BRAIN_DIARY
    assert classification.outcome == mr.OUTCOME_A


def test_outcome_a_beats_orphans():
    classification = classify({RECORDED_WING: 5, "wiki_demo_app_20261026t164600z": 3})
    assert classification.outcome == mr.OUTCOME_A


# --- scaffold drift guards ------------------------------------------------------------


def test_classifier_accepts_scaffold_generated_names():
    """The orphan pattern is built from the scaffold's WING_TS_FORMAT, so every
    name generate_wiki_wing_name can produce (timestamp, microsecond form,
    numeric suffix) must classify as an orphan candidate when unrecorded."""
    now = datetime(2026, 10, 26, 16, 46, 0, tzinfo=timezone.utc)
    base = generate_wiki_wing_name(PROJECT_DIR, now=now)
    micro = generate_wiki_wing_name(
        PROJECT_DIR, taken={base, f"wiki_{PROJECT_DIR}_20261026T164600000000Z"}, now=now
    )
    wings = {base: 1, micro: 1, base + "_2": 1}
    classification = classify(wings, recorded_wing=None, agent=None)
    assert {r.wing_class for r in classification.rows} == {mr.CLASS_ORPHAN_CANDIDATE}
    assert classification.outcome == mr.OUTCOME_B


# --- CLI (--classify-wings through main) ------------------------------------------------


WINGS_PAYLOAD = {"wings": {"demo_app": 1309, "wing_demo_app": 8}}


def make_project(tmp_path: Path) -> Path:
    root = tmp_path / PROJECT_DIR
    root.mkdir()
    return root


def test_cli_classify_wings_valid_file(tmp_path, capsys):
    root = make_project(tmp_path)
    payload = tmp_path / "wings.json"
    payload.write_text(json.dumps(WINGS_PAYLOAD), encoding="utf-8")
    assert reset_brain.main([str(root), "--classify-wings", str(payload)]) == 0
    out = capsys.readouterr().out
    assert "Received 2 wing(s), 1317 drawer(s)." in out
    assert "OUTCOME: C" in out
    assert "needs the user's confirmation" in out


def test_cli_classify_wings_stdin_bare_map(tmp_path, capsys, monkeypatch):
    root = make_project(tmp_path)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(WINGS_PAYLOAD["wings"])))
    assert reset_brain.main([str(root), "--classify-wings", "-"]) == 0
    out = capsys.readouterr().out
    assert "Received 2 wing(s), 1317 drawer(s)." in out
    assert "OUTCOME:" in out


def test_cli_classify_wings_bare_map_file(tmp_path, capsys):
    root = make_project(tmp_path)
    payload = tmp_path / "wings.json"
    payload.write_text(json.dumps(WINGS_PAYLOAD["wings"]), encoding="utf-8")
    assert reset_brain.main([str(root), "--classify-wings", str(payload)]) == 0
    assert "Received 2 wing(s)" in capsys.readouterr().out


def test_cli_classify_wings_malformed_json_exits_2(tmp_path, capsys):
    root = make_project(tmp_path)
    payload = tmp_path / "wings.json"
    payload.write_text("{not json", encoding="utf-8")
    assert reset_brain.main([str(root), "--classify-wings", str(payload)]) == 2
    assert "--classify-wings" in capsys.readouterr().err


def test_cli_classify_wings_non_dict_exits_2(tmp_path, capsys):
    root = make_project(tmp_path)
    payload = tmp_path / "wings.json"
    payload.write_text('["wings"]', encoding="utf-8")
    assert reset_brain.main([str(root), "--classify-wings", str(payload)]) == 2


def test_cli_classify_wings_non_integer_count_exits_2(tmp_path, capsys):
    root = make_project(tmp_path)
    payload = tmp_path / "wings.json"
    payload.write_text(json.dumps({"wings": {"demo_app": "1309"}}), encoding="utf-8")
    assert reset_brain.main([str(root), "--classify-wings", str(payload)]) == 2


def test_cli_nothing_recorded_slug_from_directory(tmp_path, capsys):
    root = make_project(tmp_path)  # no .brain/CLAUDE.md
    payload = tmp_path / "wings.json"
    payload.write_text(json.dumps({"wings": {"demo_app": 1309}}), encoding="utf-8")
    assert reset_brain.main([str(root), "--classify-wings", str(payload)]) == 0
    out = capsys.readouterr().out
    assert "(none recorded)" in out
    assert "Orphan-scan slug: demo_app" in out
    assert mr.CLASS_DIRECTORY_DERIVED in out
    assert mr.CLASS_ORPHAN_CANDIDATE not in out  # the directory-derived wing is never an orphan


def test_cli_reads_recorded_identity(tmp_path, capsys):
    root = make_project(tmp_path)
    brain = root / ".brain"
    brain.mkdir()
    (brain / "CLAUDE.md").write_text(
        "---\n"
        "mempalace_wing: wiki_demo_app_20261026T164600Z\n"
        "mempalace_diary_agent: brain_demo_app\n"
        "---\n",
        encoding="utf-8",
    )
    payload = tmp_path / "wings.json"
    payload.write_text(
        json.dumps({"wings": {"wiki_demo_app_20261026t164600z": 21}}), encoding="utf-8"
    )
    assert reset_brain.main([str(root), "--classify-wings", str(payload)]) == 0
    out = capsys.readouterr().out
    assert "Recorded wiki wing: wiki_demo_app_20261026T164600Z" in out
    assert mr.CLASS_BRAIN_WIKI in out
    assert "OUTCOME: A" in out


def test_cli_report_uses_no_deletion_verbs(tmp_path, capsys):
    """The output is evidence, never an instruction to act: it must not use
    deletion verbs and must end with the user-confirmation reminder."""
    root = make_project(tmp_path)
    payload = tmp_path / "wings.json"
    payload.write_text(json.dumps(incident_wings()), encoding="utf-8")
    assert reset_brain.main([str(root), "--classify-wings", str(payload)]) == 0
    out = capsys.readouterr().out.lower()
    assert "delet" not in out
    assert out.rstrip().endswith("needs the user's confirmation.")


# --- doc drift guards -----------------------------------------------------------------


def test_reset_skill_documents_classify_wings_flag():
    text = (PLUGIN_ROOT / "skills" / "reset" / "SKILL.md").read_text(encoding="utf-8")
    assert "--classify-wings" in text


def test_wing_ownership_doc_lists_every_class_name():
    """Every class label the script can emit must appear in wing-ownership.md
    (the rationale file names the script's constants)."""
    doc = (PLUGIN_ROOT / "skills" / "brain" / "references" / "wing-ownership.md").read_text(
        encoding="utf-8"
    )
    for constant in (
        mr.CLASS_BRAIN_WIKI,
        mr.CLASS_BRAIN_DIARY,
        mr.CLASS_ORPHAN_CANDIDATE,
        mr.CLASS_DIRECTORY_DERIVED,
        mr.CLASS_SESSION_OR_PATH,
        mr.CLASS_OTHER_DIARY,
        mr.CLASS_OTHER,
    ):
        assert constant in doc, f"wing-ownership.md must name the class {constant!r}"
