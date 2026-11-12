#!/usr/bin/env python3
"""Build and judge the project inventory (WP3: KD-04, KD-16).

Usage:
    brain_inventory.py <project-root> inventory [--json]
    brain_inventory.py <project-root> crossrefs
    brain_inventory.py <project-root> git-digest
    brain_inventory.py <project-root> graph-digest

inventory: list project units (git ls-files, or a directory walk honoring
  .gitignore/.graphifyignore when git is absent), classify kind + tier from
  the versioned policy (inventory-policy.json next to the plugin root), derive
  per-unit status from what the wiki actually cites (lint-validated), and
  write .brain/inventory.json atomically. Prints the uncovered work list —
  this is the resume surface for /project-brain:brain on an existing brain.

crossrefs: scan doc units for backticked path-like references, verify each
  exists, and write .brain/audit/crossrefs-report.json (exit 1 when any ref
  is missing). This receipt plus a lint --verify stamp is what licenses
  "no contradictions"-style claims (lint_brain forbidden_all_clear).

ponytail: statuses prove citation + substance (body >= STUB_MIN_BODY_CHARS),
not meaning — a page can cite a file correctly and still be wrong about it.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import lint_brain as lb

# Frozen lab constants (lab/06-frozen/constants.json). STUB_MIN_BODY_CHARS was
# chosen against real page bodies (min 299, median 490 non-ws chars, n=12).
STUB_MIN_BODY_CHARS = 120
WEIGHTED_COVERAGE_MIN = 0.90
INVENTORY_FILE = "inventory.json"
SKIPS_FILE = "inventory-skips.json"
POLICY_FILE = "inventory-policy.json"
GIT_DIGEST_REL = ".brain/raw/git/history-digest.md"
GRAPH_DIGEST_REL = ".brain/raw/graph/graph-digest.md"
GRAPH_JSON_REL = "graphify-out/graph.json"
CROSSREFS_RECEIPT = "audit/crossrefs-report.json"
# Frozen lab constants (lab/06-frozen/constants.json)
GIT_DIGEST_RECENT_COMMITS = 50
# digest bounds — named so the output stays bounded on huge repos
MAX_TAG_LINES = 20
MAX_AUTHOR_LINES = 15
MAX_AUTHOR_WINDOW_COMMITS = 1000  # ponytail: author counts over a bounded recent window, not all history
MAX_KEYWORD_COMMITS = 100
MAX_ADR_DOCS = 50
DECISION_KEYWORD_GREP = "migrate|replac|revert|remove|deprecat|rewrit|switch|refactor|renam|drop"
ADR_NAME_RE = re.compile(r"(adr|rfc|design|decision)", re.IGNORECASE)
TOP_COMMUNITIES = 10
COMMUNITY_MEMBERS_SHOWN = 8
TOP_GOD_NODES = 15
TOP_CROSS_PAIRS = 15
# ponytail: closed skip-reason list; anything else is rejected. Upgrade path:
# extend the tuple when a new legitimate reason appears, never accept free text.
SKIP_REASONS = ("generated", "vendored", "third-party", "user-directed", "not-source")
CODE_EXTS = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".py", ".go", ".rs", ".java",
             ".rb", ".php", ".c", ".h", ".cpp", ".hpp", ".cs", ".swift", ".kt", ".scala", ".sh", ".m"}
MANIFEST_BASENAMES = {"package.json", "pyproject.toml", "Cargo.toml", "go.mod", "pom.xml",
                      "requirements.txt", "setup.py", "tsconfig.json", "pytest.ini"}
# ponytail: entry-point heuristic — these stems at depth <= MAX_ENTRY_DEPTH.
ENTRY_STEMS = ("main", "index", "app", "cli", "server")
MAX_ENTRY_DEPTH = 3
WALK_SKIP_DIRS = {".git", ".brain", "graphify-out", "node_modules", "__pycache__",
                  "vendor", "dist", "build", ".venv"}
BACKTICK_RE = re.compile(r"`([^`\n]+)`")
# path-like backtick content: has a slash, or is a name.ext with a letter-leading ext
# (digit-leading extensions like 1.2 are version numbers, not paths)
PATHLIKE_RE = re.compile(r"^(?:[\w.@+-]+(?:/[\w.@+-]+)+|[\w.-]+\.[A-Za-z][A-Za-z0-9]{0,7})$")


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def atomic_write_json(path: Path, data: dict) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)  # no half-written inventory, ever


def glob_match(path_posix: str, pattern: str) -> bool:
    # ponytail: fnmatch translation — '*' crosses '/', so '**' adds nothing;
    # no brace expansion. Upgrade path: a real glob library if patterns grow.
    pat = pattern.replace("**/", "*").replace("/**", "/*").replace("**", "*")
    return fnmatch.fnmatch(path_posix, pat)


def load_policy() -> tuple[dict, Path]:
    policy_path = Path(__file__).resolve().parent.parent / POLICY_FILE
    with open(policy_path, "r", encoding="utf-8") as fh:
        return json.load(fh), policy_path


def git_ls(root: Path) -> tuple[list[str], str | None] | None:
    """(paths, HEAD) via git, or None when git is unavailable/not a repo."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            capture_output=True, text=True, timeout=60)
        head = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                              capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    paths = [p for p in proc.stdout.split("\0") if p]
    commit = head.stdout.strip() if head.returncode == 0 else None
    return paths, commit


def load_ignore_patterns(root: Path) -> list[str]:
    patterns: list[str] = []
    for name in (".gitignore", ".graphifyignore"):
        p = root / name
        if p.is_file():
            patterns.extend(p.read_text(encoding="utf-8", errors="replace").splitlines())
    return patterns


def naive_ignored(path_posix: str, patterns: list[str]) -> bool:
    # ponytail: naive gitignore — no '!' negation, no anchored patterns, no
    # '**'. Real repos go through git ls-files; this only serves no-git
    # projects. Upgrade path: `git check-ignore` when git exists.
    for raw in patterns:
        pat = raw.strip().rstrip("/")
        if not pat or pat.startswith("#") or pat.startswith("!"):
            continue
        pat = pat.lstrip("/")
        if "/" in pat:
            if fnmatch.fnmatch(path_posix, pat) or path_posix.endswith("/" + pat):
                return True
        else:
            if any(fnmatch.fnmatch(seg, pat) for seg in path_posix.split("/")):
                return True
    return False


def walk_files(root: Path) -> list[str]:
    patterns = load_ignore_patterns(root)
    out: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in WALK_SKIP_DIRS]
        for name in filenames:
            posix = (Path(dirpath) / name).relative_to(root).as_posix()
            if not naive_ignored(posix, patterns):
                out.append(posix)
    return sorted(out)


def classify(posix: str) -> str:
    parts = posix.split("/")
    name = parts[-1]
    stem, dot, ext = name.rpartition(".")
    ext = ("." + ext) if dot else ""
    low = ext.lower()
    if any(seg in ("test", "tests", "__tests__") for seg in parts):
        return "tests"
    if ".test." in name or "_test." in name or name.startswith("test_"):
        return "tests"
    if posix.startswith(".github/workflows/") or name in (".gitlab-ci.yml", "Jenkinsfile"):
        return "ci"
    if low == ".md" or "docs" in parts:
        return "docs"
    if name in MANIFEST_BASENAMES:
        return "manifest"
    if stem in ENTRY_STEMS and low in CODE_EXTS and len(parts) <= MAX_ENTRY_DEPTH:
        return "entry"
    if low in CODE_EXTS:
        return "source"
    return "other"


def tier_for(posix: str, kind: str, policy: dict) -> str:
    for rule in policy["rules"]:
        if "kind" in rule and rule["kind"] != kind:
            continue
        if "glob" in rule and not glob_match(posix, rule["glob"]):
            continue
        return rule["tier"]
    return "reference"


def unit_id(posix: str) -> str:
    return hashlib.sha256(posix.encode("utf-8")).hexdigest()[:12]


def list_units(root: Path, policy: dict) -> tuple[list[dict], str, str | None]:
    git = git_ls(root)
    if git is not None:
        paths, commit = git
        source = "git-ls-files"
    else:
        paths, commit = walk_files(root), None
        source = "directory-walk"
    deny = policy["deny_globs"]
    units = []
    for posix in sorted(set(paths)):
        if any(glob_match(posix, g) for g in deny):
            continue
        kind = classify(posix)
        units.append({"id": unit_id(posix), "path": posix, "kind": kind,
                      "tier": tier_for(posix, kind, policy)})
    units.append({"id": unit_id(GIT_DIGEST_REL), "path": GIT_DIGEST_REL,
                  "kind": "git-history", "tier": tier_for(GIT_DIGEST_REL, "git-history", policy)})
    return units, source, commit


def load_skips(brain: Path) -> dict[str, str]:
    path = brain / SKIPS_FILE
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise ValueError(f"{SKIPS_FILE} is not valid JSON: {exc}") from exc
    if not isinstance(data, list):
        raise ValueError(f"{SKIPS_FILE} must be a list of {{path, reason}} objects")
    skips: dict[str, str] = {}
    for entry in data:
        if not isinstance(entry, dict) or "path" not in entry or "reason" not in entry:
            raise ValueError(f"{SKIPS_FILE}: every entry needs 'path' and 'reason'")
        reason = str(entry["reason"]).strip()
        if reason not in SKIP_REASONS:
            raise ValueError(f"{SKIPS_FILE}: invalid reason {reason!r} "
                             f"(closed list: {', '.join(SKIP_REASONS)})")
        skips[str(entry["path"])] = reason
    return skips


def compute_statuses(root: Path, brain: Path, units: list[dict],
                     skips: dict[str, str]) -> dict[str, dict]:
    """covered = cited with a lint-passing citation by a non-draft page whose
    body carries at least STUB_MIN_BODY_CHARS of substance (KD-04, KD-16)."""
    state: dict = {}
    lb.build_report(root, citation_state=state)  # single source of truth for citation validity
    covered_by: dict[str, list[str]] = {}
    for page_rel, info in state.items():
        page = brain / page_rel
        text = lb.read(page)
        fm = lb.extract_frontmatter(text)
        if str(fm.get("status", "")).strip().lower() == "draft":
            continue
        if len(re.sub(r"\s+", "", lb.body_text(text))) < STUB_MIN_BODY_CHARS:
            continue
        for cited in info["files"]:
            norm = cited.strip()
            if norm.startswith("./"):  # never lstrip("./") — it would eat ".brain/..." leading dots
                norm = norm[2:]
            covered_by.setdefault(norm, []).append(page_rel)
    out: dict[str, dict] = {}
    for u in units:
        if u["path"] in skips:
            out[u["path"]] = {"status": "skipped", "reason": "skip: " + skips[u["path"]], "cited_by": []}
        elif u["path"] in covered_by:
            out[u["path"]] = {"status": "covered", "reason": "", "cited_by": covered_by[u["path"]]}
        else:
            out[u["path"]] = {"status": "uncovered",
                              "reason": "no valid citation from a substantive non-draft page",
                              "cited_by": []}
    return out


def cmd_inventory(root: Path, as_json: bool) -> int:
    brain = root / ".brain"
    if not brain.is_dir():
        print(f"no .brain directory at {root} — run project-brain-init first", file=sys.stderr)
        return 2
    policy, policy_path = load_policy()
    try:
        skips = load_skips(brain)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    units, source, commit = list_units(root, policy)
    by_path = {u["path"]: u for u in units}
    for path in skips:
        if path not in by_path:
            print(f"error: {SKIPS_FILE}: unknown unit path: {path}", file=sys.stderr)
            return 2
        if by_path[path]["tier"] == "core":
            print(f"error: {SKIPS_FILE}: core unit cannot be skipped: {path}", file=sys.stderr)
            return 2
    try:
        statuses = compute_statuses(root, brain, units, skips)
    except lb.VerificationCorruptError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3
    weights = policy["weights"]
    for u in units:
        u.update(statuses[u["path"]])
    oblig = [u for u in units if u["status"] != "skipped"]
    denom = sum(weights[u["tier"]] for u in oblig)
    num = sum(weights[u["tier"]] for u in oblig if u["status"] == "covered")
    weighted = round(num / denom, 4) if denom else 1.0
    core_total = sum(1 for u in oblig if u["tier"] == "core")
    core_cov = sum(1 for u in oblig if u["tier"] == "core" and u["status"] == "covered")
    complete = core_cov == core_total and weighted >= WEIGHTED_COVERAGE_MIN
    inv = {
        "version": 1,
        "generated_at": now_iso(),
        "commit": commit,
        "source": source,
        "policy": {"file": POLICY_FILE, "version": policy.get("version"),
                   "sha256": sha256_file(policy_path)},
        "stub_min_body_chars": STUB_MIN_BODY_CHARS,
        "weighted_coverage_min": WEIGHTED_COVERAGE_MIN,
        "units": units,
        "completion": {
            "core_all_covered": core_cov == core_total,
            "core_uncovered": [u["path"] for u in oblig
                               if u["tier"] == "core" and u["status"] != "covered"],
            "weighted_coverage": weighted,
            "complete": complete,
        },
        "summary": {
            "units": len(units),
            "covered": sum(1 for u in units if u["status"] == "covered"),
            "uncovered": sum(1 for u in units if u["status"] == "uncovered"),
            "skipped": sum(1 for u in units if u["status"] == "skipped"),
        },
    }
    atomic_write_json(brain / INVENTORY_FILE, inv)
    if as_json:
        print(json.dumps(inv, indent=2))
        return 0
    s, c = inv["summary"], inv["completion"]
    print(f"inventory: {s['units']} units ({source}); covered {s['covered']}, "
          f"uncovered {s['uncovered']}, skipped {s['skipped']}")
    print(f"completion: {'COMPLETE' if c['complete'] else 'INCOMPLETE'} "
          f"(core covered {core_cov}/{core_total}, weighted {c['weighted_coverage']} "
          f"vs min {WEIGHTED_COVERAGE_MIN})")
    work = [u for u in oblig if u["status"] == "uncovered" and u["tier"] in ("core", "important")]
    if work:
        print("UNCOVERED (work list):")
        for u in sorted(work, key=lambda u: (-weights[u["tier"]], u["path"])):
            print(f"  [{u['tier']}] {u['path']}")
    return 0


def cmd_crossrefs(root: Path) -> int:
    brain = root / ".brain"
    inv_path = brain / INVENTORY_FILE
    if not inv_path.is_file():
        print(f"error: no {INVENTORY_FILE} — run `project-brain-inventory <root> inventory` first",
              file=sys.stderr)
        return 2
    inv = json.loads(inv_path.read_text(encoding="utf-8"))
    doc_units = [u for u in inv["units"] if u["kind"] == "docs"]
    missing = []
    checked = 0
    for u in doc_units:
        doc = root / u["path"]
        if not doc.is_file():
            continue
        text = doc.read_text(encoding="utf-8", errors="replace")
        for ref in BACKTICK_RE.findall(text):
            ref = ref.strip()
            if ref.startswith(("http://", "https://", "~", "/")) or not PATHLIKE_RE.match(ref):
                continue
            checked += 1
            if (root / ref).exists() or (doc.parent / ref).exists():
                continue
            missing.append({"doc": u["path"], "ref": ref})
    report = {
        "generated_at": now_iso(),
        "docs_checked": len(doc_units),
        "refs_checked": checked,
        "missing": missing,
    }
    (brain / "audit").mkdir(parents=True, exist_ok=True)
    atomic_write_json(brain / CROSSREFS_RECEIPT, report)
    print(f"crossrefs: checked {checked} refs across {len(doc_units)} doc units; missing {len(missing)}")
    for m in missing:
        print(f"  MISSING  {m['doc']}: `{m['ref']}`")
    return 1 if missing else 0


def _git(root: Path, *args: str, timeout: int = 30) -> str | None:
    try:
        proc = subprocess.run(["git", "-C", str(root), *args],
                              capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return proc.stdout if proc.returncode == 0 else None


def cmd_git_digest(root: Path) -> int:
    """WP5 (KD-14): bounded, deterministic git-history digest.

    No git (or git fails) → write 'git: unavailable' and exit 0 — never fail.
    Content is timestamp-free so repeated runs are byte-identical.
    """
    brain = root / ".brain"
    if not brain.is_dir():
        print(f"no .brain directory at {root} — run project-brain-init first", file=sys.stderr)
        return 2
    out = root / GIT_DIGEST_REL  # GIT_DIGEST_REL already includes .brain/ — never join onto brain/
    out.parent.mkdir(parents=True, exist_ok=True)
    if _git(root, "rev-parse", "--git-dir") is None:
        out.write_text("# Git History Digest\n\ngit: unavailable (not a git repository)\n",
                       encoding="utf-8")
        print(f"git digest: git unavailable — placeholder written at {GIT_DIGEST_REL}")
        return 0
    branch = (_git(root, "rev-parse", "--abbrev-ref", "HEAD") or "").strip() or "(detached)"
    head = (_git(root, "rev-parse", "HEAD") or "").strip()
    count = (_git(root, "rev-list", "--count", "HEAD") or "").strip() or "0"
    tags = [t.strip() for t in (_git(root, "tag", "--list") or "").splitlines() if t.strip()][:MAX_TAG_LINES]
    author_counts: dict[str, int] = {}
    for line in (_git(root, "log", "--format=%an", "-n", str(MAX_AUTHOR_WINDOW_COMMITS)) or "").splitlines():
        name = line.strip()
        if name:
            author_counts[name] = author_counts.get(name, 0) + 1
    authors = sorted(author_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:MAX_AUTHOR_LINES]
    log = [l for l in (_git(root, "log", "-n", str(GIT_DIGEST_RECENT_COMMITS),
                            "--format=%h %s") or "").splitlines() if l.strip()]
    merges = [l for l in log
              if l.split(" ", 1)[-1].lower().startswith("merge") or "revert" in l.lower()]
    decision = [l for l in (_git(root, "log", "--regexp-ignore-case", "--extended-regexp",
                                "--grep", DECISION_KEYWORD_GREP, "-n", str(MAX_KEYWORD_COMMITS),
                                "--format=%h %s") or "").splitlines() if l.strip()]
    tracked = (_git(root, "ls-files") or "").splitlines()
    adr_docs = [f for f in tracked if ADR_NAME_RE.search(Path(f).name)][:MAX_ADR_DOCS]
    lines = [
        "# Git History Digest",
        "",
        f"- Branch: {branch}",
        f"- HEAD: {head}",
        f"- Commits: {count}",
        f"- Tags: {', '.join(tags) if tags else 'none'}",
        "",
        f"## Authors (recent {MAX_AUTHOR_WINDOW_COMMITS}-commit window)",
    ]
    lines += [f"- {name}: {n}" for name, n in authors] or ["- none"]
    lines += ["", f"## Recent subjects (last {GIT_DIGEST_RECENT_COMMITS})"]
    lines += [f"- {l}" for l in log] or ["- none"]
    lines += ["", "## Merge / revert commits (recent window)"]
    lines += [f"- {l}" for l in merges] or ["- none"]
    lines += ["", "## Decision-keyword commits (bounded)"]
    lines += [f"- {l}" for l in decision] or ["- none"]
    lines += ["", "## Design / ADR documents (tracked)"]
    lines += [f"- {f}" for f in adr_docs] or ["- none"]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"git digest: {len(log)} recent subjects, {len(decision)} decision commits -> {GIT_DIGEST_REL}")
    return 0


def cmd_graph_digest(root: Path) -> int:
    """WP6 (KD-09): digest derived ONLY from graphify-out/graph.json.

    Never copies numbers from GRAPH_REPORT.md — everything below is counted
    from the graph file itself. Missing/malformed graph fails closed (exit 2).
    """
    brain = root / ".brain"
    if not brain.is_dir():
        print(f"no .brain directory at {root} — run project-brain-init first", file=sys.stderr)
        return 2
    gj = root / GRAPH_JSON_REL
    if not gj.is_file():
        print(f"error: {GRAPH_JSON_REL} not found — run `/graphify .` first", file=sys.stderr)
        return 2
    try:
        data = json.loads(gj.read_text(encoding="utf-8"))
    except ValueError as exc:
        print(f"error: {GRAPH_JSON_REL} is malformed: {exc}", file=sys.stderr)
        return 2
    nodes = data.get("nodes")
    links = data.get("links")
    if not isinstance(nodes, list) or not isinstance(links, list):
        print(f"error: {GRAPH_JSON_REL} is malformed: nodes/links must be lists", file=sys.stderr)
        return 2
    comm: dict[object, dict] = {}
    node_comm: dict[str, object] = {}
    for n in nodes:
        cid = n.get("community") if isinstance(n.get("community"), int) else -1
        cname = str(n.get("community_name") or f"community-{cid}")
        comm.setdefault(cid, {"name": cname, "members": []})["members"].append(n)
        node_comm[str(n.get("id"))] = cid
    top_comms = sorted(comm.values(), key=lambda e: -len(e["members"]))[:TOP_COMMUNITIES]
    degree: dict[str, int] = {}
    cross: dict[tuple[str, str], int] = {}
    inferred = 0
    extracted = 0
    for e in links:
        s, t = str(e.get("source")), str(e.get("target"))
        degree[s] = degree.get(s, 0) + 1
        degree[t] = degree.get(t, 0) + 1
        if "INFER" in str(e.get("confidence") or "").upper():
            inferred += 1
        else:
            extracted += 1
        cs, ct = node_comm.get(s, -1), node_comm.get(t, -1)
        if cs != ct:
            key = (comm.get(cs, {}).get("name", "?"), comm.get(ct, {}).get("name", "?"))
            cross[key] = cross.get(key, 0) + 1
    id2node = {str(n.get("id")): n for n in nodes}
    god_ids = sorted(degree, key=lambda i: (-degree[i], i))[:TOP_GOD_NODES]
    top_cross = sorted(cross.items(), key=lambda kv: -kv[1])[:TOP_CROSS_PAIRS]
    built = data.get("built_at_commit")
    lines = [
        "# Graph Digest",
        "",
        f"- Derived from: {GRAPH_JSON_REL} (nodes: {len(nodes)}, links: {len(links)}",
        "  — counted from graph.json, not copied from any report)",
        f"- Built at commit: {built if built else 'unknown'}",
        "",
        "## Known limits of the graph",
        "- Aliased imports and some side-effect imports can be missing.",
        "- Barrel files shorten paths and supersede direct importers.",
        "- External-package edges point at package.json, not real packages.",
        "- INFERRED links are not calls; only EXTRACTED links are grounded.",
        "",
        f"- Link confidence: EXTRACTED {extracted}, INFERRED {inferred}",
        "",
        "## Largest communities",
    ]
    for e in top_comms:
        members = [str(m.get("label") or m.get("id")) for m in e["members"][:COMMUNITY_MEMBERS_SHOWN]]
        more = len(e["members"]) - len(members)
        suffix = f" (+{more} more)" if more > 0 else ""
        lines.append(f"- {e['name']} — {len(e['members'])} nodes: {', '.join(members)}{suffix}")
    lines += ["", "## God nodes (highest degree)"]
    for gid in god_ids:
        n = id2node.get(gid, {})
        lines.append(f"- {n.get('label', gid)} (degree {degree[gid]}) — {n.get('source_file', '?')}")
    lines += ["", "## Cross-community dependencies (top pairs)"]
    if top_cross:
        lines += [f"- {a} -> {b}: {c} links" for (a, b), c in top_cross]
    else:
        lines.append("- none")
    out = root / GRAPH_DIGEST_REL  # already includes .brain/ — resolve from root
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"graph digest: {len(nodes)} nodes, {len(links)} links -> {GRAPH_DIGEST_REL}")
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build and judge the project inventory.")
    parser.add_argument("project_root")
    parser.add_argument("command", choices=("inventory", "crossrefs", "git-digest", "graph-digest"))
    parser.add_argument("--json", action="store_true", dest="as_json",
                        help="inventory: print the full JSON to stdout")
    return parser.parse_args(argv[1:])


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    root = Path(args.project_root).expanduser().resolve()
    if args.command == "inventory":
        return cmd_inventory(root, args.as_json)
    if args.command == "crossrefs":
        return cmd_crossrefs(root)
    if args.command == "git-digest":
        return cmd_git_digest(root)
    return cmd_graph_digest(root)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
