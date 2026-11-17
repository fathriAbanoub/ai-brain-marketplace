#!/usr/bin/env python3
"""Check for updates to project-brain, mempalace, and graphify.

Prints installed vs latest versions. Exit 0: all current or ahead of PyPI;
1: any outdated (takes precedence); 2: none outdated, but some checks could
not be completed. Does not install anything.
"""

from __future__ import annotations

import json
import subprocess
import urllib.request
from pathlib import Path

EXIT_CURRENT = 0
EXIT_OUTDATED = 1
EXIT_UNAVAILABLE = 2
COMMAND_NOT_FOUND = 127
COMMAND_FAILED = 1
COMMAND_TIMEOUT_SECONDS = 10
PYPI_TIMEOUT_SECONDS = 8
ZERO_VERSION_COMPONENT = 0
LAST_VERSION_COMPONENT_INDEX = -1
NOT_INSTALLED = "not installed"
PYPI_ERROR_PREFIX = "error"

MEMPALACE_UPGRADE_COMMAND = "uv tool install mempalace --upgrade"
GRAPHIFY_UPGRADE_COMMAND = "uv tool install graphifyy --upgrade"


def run(*cmd: str, timeout: int = COMMAND_TIMEOUT_SECONDS) -> tuple[int, str]:
    try:
        proc = subprocess.run(list(cmd), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout)
        return proc.returncode, proc.stdout.strip()
    except FileNotFoundError:
        return COMMAND_NOT_FOUND, f"not found: {cmd[0]}"
    except Exception as exc:
        return COMMAND_FAILED, str(exc)


def pypi_latest(package: str) -> str:
    url = f"https://pypi.org/pypi/{package}/json"
    try:
        with urllib.request.urlopen(url, timeout=PYPI_TIMEOUT_SECONDS) as resp:
            data = json.loads(resp.read())
            return data["info"]["version"]
    except Exception as exc:
        return f"{PYPI_ERROR_PREFIX}: {exc}"


def numeric_version_key(version: str | None) -> tuple[int, ...] | None:
    """Dotted-numeric key ignoring trailing zeros; None when unparseable."""
    # ponytail: ceiling dotted-numeric releases; use a PEP 440 parser if suffix ordering is needed.
    if not isinstance(version, str):
        return None
    parts = version.split(".")
    if not all(part.isdecimal() for part in parts):
        return None
    try:
        key = [int(part) for part in parts]
    except ValueError:
        return None
    while key and key[LAST_VERSION_COMPONENT_INDEX] == ZERO_VERSION_COMPONENT:
        key.pop()
    return tuple(key)


def highest_version_name(names: list[str]) -> str | None:
    """Highest dotted-numeric version name; numeric compare, so "0.10.0"
    sorts above "0.9.4" (a string sort would put "0.10.0" first). Names that
    are not fully dotted-numeric are ignored. Trailing zeros are equivalent;
    the first name wins ties. None when nothing qualifies."""
    best_name = None
    best_key: tuple[int, ...] | None = None
    for name in names:
        key = numeric_version_key(name)
        if key is None:
            continue
        if best_key is None or key > best_key:
            best_key, best_name = key, name
    return best_name


def openclaude_plugin_version(plugin_key: str) -> str:
    """Return the highest dotted-numeric version in the OpenClaude plugin cache."""
    cache = Path.home() / ".openclaude" / "plugins" / "cache"
    # plugin_key is e.g. "mempalace/mempalace"
    parts = plugin_key.split("/")
    plugin_dir = cache.joinpath(*parts)
    if not plugin_dir.exists():
        return NOT_INSTALLED
    highest = highest_version_name([d.name for d in plugin_dir.iterdir() if d.is_dir()])
    return highest or NOT_INSTALLED


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

    # ponytail: ceiling two PyPI tools plus one cache fallback; expand this loop if another tool is added.
    for tool, package, upgrade_command in (
        ("mempalace", "mempalace", MEMPALACE_UPGRADE_COMMAND),
        ("graphify", "graphifyy", GRAPHIFY_UPGRADE_COMMAND),
    ):
        cache = openclaude_plugin_version("mempalace/mempalace") if tool == "mempalace" else NOT_INSTALLED
        rc, binary = run(tool, "--version")
        bin_ver = binary.split().pop() if rc == EXIT_CURRENT and binary.strip() else None
        latest = pypi_latest(package)
        print(f"{tool}:")
        if tool == "mempalace":
            print(f"  plugin cache:  {cache}")
        print(f"  binary:        {bin_ver or 'not on PATH'}")
        suffix = f"  (package: {package})" if package != tool else ""
        print(f"  PyPI latest:   {latest}{suffix}")
        if bin_ver is None:
            print("  ⚠  binary unavailable — update status unknown")
            unavailable = True
        if isinstance(latest, str) and latest.startswith(PYPI_ERROR_PREFIX):
            print("  ⚠  PyPI check failed — update status unknown")
            unavailable = True
        else:
            installed = bin_ver if bin_ver is not None else cache
            label = "plugin cache" if bin_ver is None and tool == "mempalace" else "binary"
            installed_key = numeric_version_key(installed)
            latest_key = numeric_version_key(latest)
            if latest_key is None or (installed != NOT_INSTALLED and installed_key is None):
                print(f"  ⚠  cannot compare {label} ({installed}) with PyPI ({latest}) — update status unknown")
                unavailable = True
            elif installed_key is not None:
                if installed_key < latest_key:
                    print(f"  ⚠  {label} is behind PyPI — run: {upgrade_command}")
                    outdated = True
                elif installed_key > latest_key:
                    print(f"  ✓  {label} is ahead of PyPI (pre-release or local build)")
                else:
                    print(f"  ✓  {label} is current")
        print()

    if outdated:
        print("Some tools are outdated. Review the update commands above.")
        return EXIT_OUTDATED
    if unavailable:
        print("Some checks could not be completed (binary unavailable, PyPI unavailable, or unparseable version).")
        return EXIT_UNAVAILABLE
    print("All tools are current or ahead of PyPI.")
    return EXIT_CURRENT


if __name__ == "__main__":
    raise SystemExit(main())
