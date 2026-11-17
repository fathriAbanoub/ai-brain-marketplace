"""Offline update-check regressions: numeric ordering, status, and wrapper roots.

Run the status and wrapper checks without a test framework:
    python3 tests/test_update_check.py
"""

import os
import stat
import subprocess
import sys
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))

import update_check  # noqa: E402

EXIT_CURRENT = 0
EXIT_OUTDATED = 1
EXIT_UNAVAILABLE = 2
COMMAND_NOT_FOUND = 127
WRAPPER_TIMEOUT_SECONDS = 10
WRAPPER_COPY_CEILING = 9

TOOL_COMMANDS = (
    ("mempalace", "mempalace", "uv tool install mempalace --upgrade"),
    ("graphify", "graphifyy", "uv tool install graphifyy --upgrade"),
)
WRAPPER_SCRIPTS = {
    "project-brain-audit-open": "audit_review.py",
    "project-brain-doctor": "doctor.py",
    "project-brain-hard-reset": "hard_reset.py",
    "project-brain-init": "scaffold_brain.py",
    "project-brain-inventory": "brain_inventory.py",
    "project-brain-lint": "lint_brain.py",
    "project-brain-reset": "reset_brain.py",
    "project-brain-update-check": "update_check.py",
    "project-brain-wiki": "wiki_ledger.py",
}


def run_check(installed=None, latest=None, cache=update_check.NOT_INSTALLED):
    """Keep reporting real; replace only local/PyPI version discovery."""
    installed = {"mempalace": "0.10.0", "graphify": "0.10.0", **(installed or {})}
    latest = {"mempalace": "0.10.0", "graphifyy": "0.10.0", **(latest or {})}
    binaries = {
        tool: (EXIT_CURRENT, f"{tool} {version}") if version is not None
        else (COMMAND_NOT_FOUND, f"not found: {tool}")
        for tool, version in installed.items()
    }
    output = StringIO()
    with (
        patch.object(update_check, "run", side_effect=lambda tool, *args: binaries[tool]),
        patch.object(update_check, "pypi_latest", side_effect=latest.__getitem__),
        patch.object(update_check, "plugin_brain_version", return_value="0.10.2"),
        patch.object(update_check, "openclaude_plugin_version", return_value=cache),
        redirect_stdout(output),
    ):
        rc = update_check.main()
    return rc, output.getvalue()


def test_binary_version_status():
    cases = (
        ("0.10.0", "0.9.4", EXIT_CURRENT, "ahead of PyPI (pre-release or local build)"),
        ("0.10.0", "0.10.0", EXIT_CURRENT, "binary is current"),
        ("0.9.4", "0.10.0", EXIT_OUTDATED, "binary is behind PyPI"),
        ("local-build", "0.10.0", EXIT_UNAVAILABLE, "cannot compare"),
        ("0.10.0", "invalid", EXIT_UNAVAILABLE, "cannot compare"),
        ("².1", "0.10.0", EXIT_UNAVAILABLE, "cannot compare"),
        ("0.10.0", None, EXIT_UNAVAILABLE, "cannot compare"),
    )
    for tool, package, command in TOOL_COMMANDS:
        for installed, latest, expected_rc, status in cases:
            rc, output = run_check({tool: installed}, {package: latest})
            assert rc == expected_rc, output
            _, _, section = output.partition(f"{tool}:\n")
            section, _, _ = section.partition("\n\n")
            assert status in section, output
            if expected_rc == EXIT_OUTDATED:
                assert command in output, output
                assert "Some tools are outdated." in output, output
                assert "Some checks could not be completed" not in output, output
            else:
                assert "uv tool install" not in output, output
                assert "outdated" not in output, output
            if expected_rc == EXIT_UNAVAILABLE:
                assert "unknown" in section, output
                assert "current" not in section and "behind PyPI" not in section, output
                assert "All tools are" not in output, output
                assert "Some checks could not be completed" in output, output


def test_outdated_binaries_print_effective_upgrade_commands():
    rc, output = run_check({"mempalace": "0.9.4", "graphify": "0.9.4"})
    assert rc == EXIT_OUTDATED, output
    for _, _, command in TOOL_COMMANDS:
        assert command in output, output


def test_missing_tool_or_pypi_failure_is_unknown():
    for tool, package, command in TOOL_COMMANDS:
        for installed, latest in (
            (None, "0.10.0"),
            ("0.10.0", f"{update_check.PYPI_ERROR_PREFIX}: offline"),
        ):
            rc, output = run_check({tool: installed}, {package: latest})
            assert rc == EXIT_UNAVAILABLE, output
            _, _, section = output.partition(f"{tool}:\n")
            section, _, _ = section.partition("\n\n")
            assert "unknown" in section, output
            assert "outdated" not in output and command not in output, output
            assert "All tools are" not in output, output


def test_missing_graphify_with_invalid_pypi_version_never_claims_a_cache():
    rc, output = run_check({"graphify": None}, {"graphifyy": None})
    assert rc == EXIT_UNAVAILABLE, output
    _, _, section = output.partition("graphify:\n")
    section, _, _ = section.partition("\n\n")
    assert "unknown" in section and "cannot compare" in section, output
    assert "plugin cache" not in section, output


def test_plugin_cache_version_status_without_binary():
    cases = (
        ("0.10.0", "0.9.4", "ahead of PyPI (pre-release or local build)", False),
        ("0.10.0", "0.10.0", "plugin cache is current", False),
        ("0.9.4", "0.10.0", "behind PyPI", True),
        ("local-build", "0.10.0", "cannot compare", False),
        ("0.10.0", "invalid", "cannot compare", False),
    )
    for installed, latest, status, behind in cases:
        rc, output = run_check({"mempalace": None}, {"mempalace": latest}, cache=installed)
        # A known outdated cache takes precedence; otherwise the missing CLI is unavailable.
        assert rc == (EXIT_OUTDATED if behind else EXIT_UNAVAILABLE), output
        _, _, section = output.partition("mempalace:\n")
        section, _, _ = section.partition("\n\n")
        assert status in section, output
        assert "unknown" in section, output
        if behind:
            assert "uv tool install mempalace --upgrade" in output, output
        else:
            assert "uv tool install" not in output and "outdated" not in output, output


def test_outdated_tool_takes_precedence_over_unavailable_check():
    for installed, command in (
        ({"mempalace": "local-build", "graphify": "0.9.4"}, "uv tool install graphifyy --upgrade"),
        ({"mempalace": "0.9.4", "graphify": None}, "uv tool install mempalace --upgrade"),
    ):
        rc, output = run_check(installed)
        assert rc == EXIT_OUTDATED, output
        assert "unknown" in output and command in output, output
        assert "Some tools are outdated." in output, output
        assert "Some checks could not be completed" not in output, output
        assert "All tools are" not in output, output


def test_trailing_zero_version_components_are_equivalent():
    for tool, package, command in TOOL_COMMANDS:
        for installed, latest, expected_rc, status in (
            ("1.0", "1.0.0", EXIT_CURRENT, "binary is current"),
            ("1.0.0", "1.0", EXIT_CURRENT, "binary is current"),
            ("1.0", "1.0.1", EXIT_OUTDATED, "binary is behind PyPI"),
            ("0.0", "0", EXIT_CURRENT, "binary is current"),
        ):
            rc, output = run_check({tool: installed}, {package: latest})
            assert rc == expected_rc, output
            _, _, section = output.partition(f"{tool}:\n")
            section, _, _ = section.partition("\n\n")
            assert status in section, output
            assert (command in output) == (expected_rc == EXIT_OUTDATED), output
    assert update_check.highest_version_name(["1.0", "0.9"]) == "1.0"


def test_wrappers_find_their_script_with_invalid_and_valid_roots():
    wrappers = [
        path for path in sorted((PLUGIN_ROOT / "bin").iterdir())
        if "CLAUDE_PLUGIN_ROOT" in path.read_text(encoding="utf-8")
    ]
    # ponytail: ceiling nine inline copies; source a shared helper at the tenth wrapper.
    assert len(wrappers) == WRAPPER_COPY_CEILING
    assert {path.name for path in wrappers} == set(WRAPPER_SCRIPTS)
    with TemporaryDirectory(prefix="update-check-") as temporary:
        base = Path(temporary)
        local_root = base / "plugin copy"
        foreign_root = base / "valid foreign plugin"
        incomplete_root = base / "missing target script"
        (local_root / "bin").mkdir(parents=True)
        for root in (local_root, foreign_root, incomplete_root):
            (root / "scripts").mkdir(parents=True)
        file_root = base / "not a directory"
        file_root.write_text("not a plugin", encoding="utf-8")
        # ponytail: dispatch-only stubs prevent network/deletion in nine wrappers;
        # use script-specific integration fixtures if wrapper argument handling changes.
        script = "from pathlib import Path\nprint(Path(__file__).resolve())\n"
        for wrapper in wrappers:
            script_name = WRAPPER_SCRIPTS[wrapper.name]
            for root in (local_root, foreign_root):
                (root / "scripts" / script_name).write_text(script, encoding="utf-8")
            copy = local_root / "bin" / wrapper.name
            copy.write_text(wrapper.read_text(encoding="utf-8"), encoding="utf-8")
            copy.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
            for inherited, expected in (
                (base / "nonexistent plugin", local_root),
                (incomplete_root, local_root),
                (file_root, local_root),
                (foreign_root, foreign_root),
                (None, local_root),
                ("", local_root),
            ):
                env = {key: value for key, value in os.environ.items() if key != "CLAUDE_PLUGIN_ROOT"}
                env["PYTHON_BIN"] = sys.executable
                if inherited is not None:
                    env["CLAUDE_PLUGIN_ROOT"] = str(inherited)
                proc = subprocess.run(
                    [str(copy), str(base / "project"), "--dry-run"], cwd=base, env=env,
                    capture_output=True, text=True, timeout=WRAPPER_TIMEOUT_SECONDS,
                )
                assert proc.returncode == EXIT_CURRENT, f"{wrapper.name}: {proc.stderr}"
                assert proc.stdout.strip() == str(expected / "scripts" / script_name), proc.stdout


class TestHighestVersionName:
    def test_zero_ten_sorts_above_zero_nine(self):
        assert update_check.highest_version_name(["0.9.4", "0.10.0"]) == "0.10.0"

    def test_numeric_not_lexicographic(self):
        # Lexicographic would pick "0.9.4" here ("4" > "1" charwise).
        names = ["0.9.4", "0.9.10"]
        assert update_check.highest_version_name(names) == "0.9.10"

    def test_equivalent_versions_keep_the_first_name(self):
        assert update_check.highest_version_name(["0.10", "0.10.0"]) == "0.10"
        assert update_check.highest_version_name(["0.10.0", "0.10"]) == "0.10.0"

    def test_non_numeric_names_are_ignored(self):
        names = ["0.9.4", "0.10.0-beta", "latest", "0.11.0"]
        assert update_check.highest_version_name(names) == "0.11.0"

    def test_empty_and_all_invalid_return_none(self):
        assert update_check.highest_version_name([]) is None
        assert update_check.highest_version_name(["beta", "x.y"]) is None

    def test_cache_scan_uses_the_numeric_helper(self, tmp_path, monkeypatch):
        """openclaude_plugin_version picks 0.10.0 from a cache shaped like the
        real plugin cache (~/.openclaude/plugins/cache/<plugin>/<version>/)."""
        cache = tmp_path / ".openclaude" / "plugins" / "cache" / "mempalace" / "mempalace"
        for name in ("0.9.4", "0.10.0", "notes"):
            (cache / name).mkdir(parents=True)
        monkeypatch.setattr("pathlib.Path.home", lambda *args, **kwargs: tmp_path)
        assert update_check.openclaude_plugin_version("mempalace/mempalace") == "0.10.0"

    def test_cache_scan_without_versions(self, tmp_path, monkeypatch):
        cache = tmp_path / ".openclaude" / "plugins" / "cache" / "mempalace" / "mempalace"
        cache.mkdir(parents=True)
        monkeypatch.setattr("pathlib.Path.home", lambda *args, **kwargs: tmp_path)
        assert update_check.openclaude_plugin_version("mempalace/mempalace") == update_check.NOT_INSTALLED


if __name__ == "__main__":
    test_binary_version_status()
    test_outdated_binaries_print_effective_upgrade_commands()
    test_missing_tool_or_pypi_failure_is_unknown()
    test_missing_graphify_with_invalid_pypi_version_never_claims_a_cache()
    test_plugin_cache_version_status_without_binary()
    test_outdated_tool_takes_precedence_over_unavailable_check()
    test_trailing_zero_version_components_are_equivalent()
    test_wrappers_find_their_script_with_invalid_and_valid_roots()
    print("update-check status and wrapper assertions passed")
