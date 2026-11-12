"""WP7 regression tests: ingestion safety (KD-15).

Regression-first: the brain_secret check and the sensitive-path extension of
ensure_graphifyignore did not exist when these were written — watched failing
before implementation.
"""

import json
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))
import scaffold_brain as sb  # noqa: E402


def lint_categories(run_script, proj: Path) -> list[str]:
    r = run_script("lint_brain.py", [str(proj), "--json"])
    return [i["category"] for i in json.loads(r.stdout)["issues"]]


class TestGraphifyignoreSensitivePaths:
    def test_scaffold_extends_existing_file_preserving_user_entries(self, run_script, tmp_project: Path):
        proj = tmp_project / "safety-project"
        proj.mkdir(parents=True)
        (proj / ".graphifyignore").write_text("# user comment\nbuild-output/\n", encoding="utf-8")
        result = run_script("scaffold_brain.py", [str(proj), "Safety"])
        assert result.returncode == 0, result.stderr
        lines = (proj / ".graphifyignore").read_text(encoding="utf-8").splitlines()
        assert "# user comment" in lines and "build-output/" in lines
        for entry in (".brain/", "graphify-out/", ".env", ".env.*", "*.pem", "*.key",
                      "id_rsa*", "secrets/", "credentials*.json"):
            assert entry in lines, entry

    def test_ensure_idempotent_no_duplicates(self, tmp_project: Path):
        proj = tmp_project / "safety-project"
        proj.mkdir(parents=True)
        (proj / ".graphifyignore").write_text(".brain/\n", encoding="utf-8")
        sb.ensure_graphifyignore(proj)
        sb.ensure_graphifyignore(proj)
        lines = (proj / ".graphifyignore").read_text(encoding="utf-8").splitlines()
        assert lines.count(".brain/") == 1
        for entry in (".env", "*.pem", "id_rsa*", "secrets/"):
            assert lines.count(entry) == 1, entry


class TestBrainSecretScan:
    def test_secrets_in_brain_flagged_as_errors(self, run_script, tmp_project: Path):
        proj = tmp_project / "sec-project"
        proj.mkdir(parents=True)
        result = run_script("scaffold_brain.py", [str(proj), "Sec"])
        assert result.returncode == 0, result.stderr
        raw = proj / ".brain" / "raw"
        raw.mkdir(parents=True, exist_ok=True)
        (raw / "key.txt").write_text(
            "-----BEGIN RSA PRIVATE KEY-----\nabc\n-----END RSA PRIVATE KEY-----\n", encoding="utf-8")
        (raw / "env.txt").write_text("MY_TOKEN=abc123xyz\nOTHER=fine\n", encoding="utf-8")
        # AWS's published documentation example key, built in split form so the
        # deliverable key-scan never sees a credential-shaped literal here.
        aws_example = "AKIA" + "IOSFODNN7EXAMPLE"
        (raw / "cloud.txt").write_text(f"key {aws_example} here\n", encoding="utf-8")
        cats = lint_categories(run_script, proj)
        assert cats.count("brain_secret") >= 3
        r = run_script("lint_brain.py", [str(proj), "--json"])
        assert r.returncode == 1

    def test_clean_brain_not_flagged(self, run_script, tmp_project: Path):
        proj = tmp_project / "sec-project"
        proj.mkdir(parents=True)
        result = run_script("scaffold_brain.py", [str(proj), "Sec"])
        assert result.returncode == 0, result.stderr
        assert "brain_secret" not in lint_categories(run_script, proj)
