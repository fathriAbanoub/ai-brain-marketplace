"""KD-20 regression tests: graphify invocation policy and plugin-root
persistence.

0.9.x history (kept for context): the skill taught `/graphify .` first, and in
a CLI-only environment the inner model ran `/graphify .` AS A BASH COMMAND,
got "No such file or directory", and burned turns searching for a plugin-owned
graphify before dying. Tool messages therefore had to teach the CLI form.

0.10.0 policy REVERSAL (deliberate pin migration): a live 50-turn session
showed the CLI-first rule costs more than it saves — the CLI needs an API
backend (`GRAPHIFY_BACKEND=none` on BOTH `extract` and `cluster-only`, or you
get "Community N" placeholders) and the MCP query tools need an already-built
graph anyway. The `/graphify` skill is now PRIMARY (the agent runs the
semantic pass itself; no extra packages, no slash-form-in-shell hazard because
it is invoked as a skill, not typed into Bash); the CLI is FALLBACK-ONLY and
every message that names it must label it as the fallback. The slash form is
STILL forbidden as a shell command in tool messages (the old hazard is real).

Unchanged: the resolved plugin root must be persistable across shells — every
new shell re-deriving PLUGIN_ROOT burned turns (multi-turn search dance) even
though a previous shell in the same project had already resolved it.
"""

import re
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = PLUGIN_ROOT / "skills"

IMPERATIVE_SLASH_RE = re.compile(r"(run|rebuild with|Use) `/graphify \.`")
STATE_FILE = ".brain/state/plugin-root.txt"


def skills_with_fallback() -> list[Path]:
    out = []
    for skill_md in sorted(SKILLS_DIR.glob("*/SKILL.md")):
        if 'PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-}"' in skill_md.read_text(encoding="utf-8"):
            out.append(skill_md)
    return out


class TestGraphifySkillFirst:
    """0.10.0: the /graphify skill is primary; the CLI is fallback-only.
    Migrated from the 0.9.x CLI-first pins — see the module docstring."""

    @pytest.mark.parametrize("src", [
        PLUGIN_ROOT / "scripts" / "lint_brain.py",
        PLUGIN_ROOT / "scripts" / "doctor.py",
    ], ids=["lint_brain", "doctor"])
    def test_tool_messages_name_skill_primary_cli_fallback(self, src: Path):
        text = src.read_text(encoding="utf-8")
        # The slash form is still never taught as a shell command.
        hits = IMPERATIVE_SLASH_RE.findall(text)
        assert not hits, (
            f"{src.name}: the `/graphify .` slash form must never appear as a "
            "shell command — it fails when typed into Bash (observed live)"
        )
        # Skill-first policy: the primary builder is named.
        assert "/graphify" in text, (
            f"{src.name}: tool messages must name the /graphify skill as the "
            "primary builder"
        )
        # The CLI still appears, as the labeled fallback.
        assert "graphify .`" in text, (
            f"{src.name}: the CLI fallback form `graphify .` must be named"
        )
        assert "fallback" in text.lower(), (
            f"{src.name}: every CLI mention must be labeled as the fallback"
        )

    def test_brain_skill_step3_names_skill_primary(self):
        text = (SKILLS_DIR / "brain" / "SKILL.md").read_text(encoding="utf-8")
        assert "primary: the `/graphify` skill" in text, (
            "brain/SKILL.md step 3 must present the /graphify skill as the "
            "primary builder (0.10.0 policy; see module docstring)"
        )
        assert "`graphify .`" in text, (
            "brain/SKILL.md must still name the CLI form as the fallback"
        )

    def test_brain_skill_has_no_imperative_slash_form(self):
        text = (SKILLS_DIR / "brain" / "SKILL.md").read_text(encoding="utf-8")
        hits = IMPERATIVE_SLASH_RE.findall(text)
        assert not hits, (
            "brain/SKILL.md: the `/graphify .` slash form must never be "
            "presented as a shell command"
        )


class TestPluginRootPersistence:
    @pytest.mark.parametrize("skill_md", skills_with_fallback(), ids=lambda p: p.parent.name)
    def test_state_file_documented(self, skill_md: Path):
        text = skill_md.read_text(encoding="utf-8")
        assert STATE_FILE in text, (
            f"{skill_md}: after a successful resolution the plugin root should "
            f"be persisted to {STATE_FILE} so later shells load it with one "
            "command instead of repeating the search dance (observed live: "
            "multi-turn re-derivation in every new shell)"
        )

    @pytest.mark.parametrize("skill_md", skills_with_fallback(), ids=lambda p: p.parent.name)
    def test_staleness_check_documented(self, skill_md: Path):
        text = skill_md.read_text(encoding="utf-8")
        # the load must be guarded: a stale path must fall back to re-resolution
        assert "plugin-root.txt" in text and (
            '-d "$PLUGIN_ROOT/bin"' in text or '-x "$PLUGIN_ROOT/bin' in text
        ), (
            f"{skill_md}: loading the persisted plugin root must include a "
            "staleness check (bin/ must exist) before use"
        )
