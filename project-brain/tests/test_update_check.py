"""update_check.py: version comparison must be NUMERIC.

"0.10.0" must sort above "0.9.4" — a lexicographic string comparison puts
"0.10.0" before "0.9.4" and would report the older version as installed. The
ordering lives in highest_version_name() (one testable seam used by
openclaude_plugin_version for the plugin-cache directory scan).
"""

import pathlib
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))

import update_check  # noqa: E402


class TestHighestVersionName:
    def test_zero_ten_sorts_above_zero_nine(self):
        assert update_check.highest_version_name(["0.9.4", "0.10.0"]) == "0.10.0"

    def test_numeric_not_lexicographic(self):
        # Lexicographic would pick "0.9.4" here ("4" > "1" charwise).
        names = ["0.9.4", "0.9.10"]
        assert update_check.highest_version_name(names) == "0.9.10"

    def test_longer_version_wins_on_equal_prefix(self):
        assert update_check.highest_version_name(["0.10", "0.10.0"]) == "0.10.0"

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
        assert update_check.openclaude_plugin_version("mempalace/mempalace") == "not installed"
