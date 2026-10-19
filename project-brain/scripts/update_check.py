#!/usr/bin/env python3
"""Check for updates to project-brain, mempalace, and graphify.

Prints installed vs latest versions and exits 0 if all current, 1 if any outdated.
Does not install anything.
"""

from __future__ import annotations

import json
import subprocess
import sys
import urllib.request
from pathlib import Path


def run(*cmd: str, timeout: int = 10) -> tuple[int, str]:
    try:
        proc = subprocess.run(list(cmd), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout)
        return proc.returncode, proc.stdout.strip()
    except FileNotFoundError:
        return 127, f"not found: {cmd[0]}"
    except Exception as exc:
        return 1, str(exc)


def pypi_latest(package: str) -> str:
    url = f"https://pypi.org/pypi/{package}/json"
    try:
        with urllib.request.urlopen(url, timeout=8) as resp:
            data = json.loads(resp.read())
            return data["info"]["version"]
    except Exception as exc:
        return f"error: {exc}"


def openclaude_plugin_version(plugin_key: str) -> str:
    """Return the highest semver installed in the OpenClaude plugin cache."""
    import re
    cache = Path.home() / ".openclaude" / "plugins" / "cache"
    # plugin_key is e.g. "mempalace/mempalace"
    parts = plugin_key.split("/")
    plugin_dir = cache.joinpath(*parts)
    if not plugin_dir.exists():
        return "not installed"
    versions = []
    for d in plugin_dir.iterdir():
        if d.is_dir():
            try:
                segments = tuple(int(x) for x in d.name.split("."))
                versions.append((segments, d.name))
            except ValueError:
                pass
    if not versions:
        return "not installed"
    versions.sort(reverse=True)
    return versions[0][1]


def plugin_brain_version() -> str:
    """Read version from the plugin.json of the ai-brain-marketplace plugin."""
    candidates = [
        Path.home() / ".openclaude" / "plugins" / "marketplaces" / "ai-brain-marketplace" / "project-brain" / ".claude-plugin" / "plugin.json",
        Path.home() / ".openclaude" / "plugins" / "marketplaces" / "ai-brain-marketplace" / ".claude-plugin" / "plugin.json",
        Path(__file__).parent.parent / ".claude-plugin" / "plugin.json",
    ]
    for p in candidates:
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                return data.get("version", "unknown")
            except Exception:
                pass
    return "unknown"


def main() -> int:
    outdated = False
    unavailable = False
    print("project-brain update check\n")

    # --- project-brain plugin ---
    brain_ver = plugin_brain_version()
    installed_path = Path.home() / ".openclaude" / "plugins" / "marketplaces" / "ai-brain-marketplace"
    print(f"project-brain plugin:  installed={brain_ver}")
    print(f"  (local marketplace — check {installed_path} for the latest version)")
    print()

    # --- mempalace ---
    mempalace_cache = openclaude_plugin_version("mempalace/mempalace")
    rc, mempalace_bin = run("mempalace", "--version")
    bin_ver = mempalace_bin.split()[-1] if rc == 0 and mempalace_bin else None
    latest_mp = pypi_latest("mempalace")
    print(f"mempalace:")
    print(f"  plugin cache:  {mempalace_cache}")
    if bin_ver:
        print(f"  binary:        {bin_ver}")
    else:
        print(f"  binary:        not on PATH")
        unavailable = True
    print(f"  PyPI latest:   {latest_mp}")
    if latest_mp.startswith("error"):
        print(f"  ⚠  PyPI check failed — update status unknown")
        unavailable = True
    elif bin_ver and latest_mp != bin_ver:
        print(f"  ⚠  binary is behind PyPI — run: uv tool install mempalace")
        outdated = True
    elif bin_ver:
        print(f"  ✓  binary is current")
    if not bin_ver and not latest_mp.startswith("error") and mempalace_cache not in ("not installed",):
        if latest_mp != mempalace_cache:
            print(f"  ⚠  plugin cache ({mempalace_cache}) may be behind PyPI ({latest_mp})")
            outdated = True
    print()

    # --- graphify ---
    rc, graphify_bin = run("graphify", "--version")
    graphify_ver = graphify_bin.split()[-1] if rc == 0 and graphify_bin else None
    latest_gf = pypi_latest("graphifyy")  # double-y is the package name
    print(f"graphify:")
    if graphify_ver:
        print(f"  binary:        {graphify_ver}")
    else:
        print(f"  binary:        not on PATH")
        unavailable = True
    print(f"  PyPI latest:   {latest_gf}  (package: graphifyy)")
    if latest_gf.startswith("error"):
        print(f"  ⚠  PyPI check failed — update status unknown")
        unavailable = True
    elif graphify_ver and latest_gf != graphify_ver:
        print(f"  ⚠  binary is behind PyPI — run: uv tool install graphifyy")
        outdated = True
    elif graphify_ver:
        print(f"  ✓  binary is current")
    print()

    if outdated:
        print("Some tools are outdated. Review the update commands above.")
        return 1
    if unavailable:
        print("Some checks could not be completed (binary not on PATH or PyPI unavailable).")
        return 2
    print("All tools are current.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
