"""Test that graphify guidance does not offer unconditional OR choice."""

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
SKILL_DIR = PROJECT_ROOT / "skills" / "brain"
REFS_DIR = SKILL_DIR / "references"

# Files that should have the conditional decision rule
FILES_TO_CHECK = [
    SKILL_DIR / "SKILL.md",
    REFS_DIR / "brain-lifecycle.md",
    REFS_DIR / "post-wiki-checklist.md",
]

# Pattern that would indicate unconditional OR choice (forbidden)
# Groups the two command alternatives so the explicit OR between them is required
UNCONDITIONAL_OR_PATTERN = re.compile(
    r"(?:Run|run)\s+(?:`/graphify \.`|`graphify update \.`)\s+(?:OR|or)\s+(?:`/graphify \.`|`graphify update \.`)",
    re.IGNORECASE
)

# Pattern that should exist: conditional choice based on doctor reason
CONDITIONAL_PATTERN = re.compile(
    r"(?:Reason|reason)\s+starts\s+with.*?graphify-out/GRAPH_REPORT\.md missing.*?graph built at",
    re.IGNORECASE | re.DOTALL
)


def test_no_unconditional_or_choice():
    """Verify docs don't say 'run X OR Y' without checking doctor reason."""
    violations = []

    for file_path in FILES_TO_CHECK:
        if not file_path.exists():
            violations.append(f"Missing file: {file_path}")
            continue

        content = file_path.read_text()

        # Check for forbidden unconditional OR
        if UNCONDITIONAL_OR_PATTERN.search(content):
            violations.append(
                f"{file_path.relative_to(PROJECT_ROOT)}: "
                "Found unconditional 'X OR Y' pattern without doctor reason check"
            )

    assert not violations, "\n".join(violations)


def test_conditional_guidance_present():
    """Verify docs include conditional decision rule based on doctor reason."""
    missing = []

    for file_path in FILES_TO_CHECK:
        if not file_path.exists():
            missing.append(f"Missing file: {file_path}")
            continue

        content = file_path.read_text()

        # Check for required conditional pattern
        if not CONDITIONAL_PATTERN.search(content):
            missing.append(
                f"{file_path.relative_to(PROJECT_ROOT)}: "
                "Missing conditional decision rule based on doctor reason"
            )

    assert not missing, "\n".join(missing)


def test_doctor_reason_strings_documented():
    """Verify docs reference exact doctor.py reason strings."""
    required_strings = [
        "graphify-out/GRAPH_REPORT.md missing",
        "graph built at",
        "uncommitted changes to source files:",
    ]

    violations = []

    for file_path in FILES_TO_CHECK:
        if not file_path.exists():
            continue

        content = file_path.read_text()

        missing_in_file = [s for s in required_strings if s not in content]
        if missing_in_file:
            violations.append(
                f"{file_path.relative_to(PROJECT_ROOT)}: "
                f"Missing reason strings: {', '.join(repr(s) for s in missing_in_file)}"
            )

    assert not violations, "\n".join(violations)


def test_conditional_sentence_not_flagged():
    """Verify that conditional sentences with graphify commands are NOT flagged."""
    conditional = "Run `/graphify .` when the report is missing."
    assert not UNCONDITIONAL_OR_PATTERN.search(conditional)


def test_unconditional_or_is_flagged():
    """Verify that unconditional OR patterns ARE flagged."""
    unconditional_1 = "Run `/graphify .` OR `graphify update .`"
    unconditional_2 = "Run `graphify update .` or `/graphify .`"

    assert UNCONDITIONAL_OR_PATTERN.search(unconditional_1), \
        "Should flag: /graphify . OR graphify update ."
    assert UNCONDITIONAL_OR_PATTERN.search(unconditional_2), \
        "Should flag: graphify update . or /graphify ."


def test_current_docs_pass():
    """Verify current docs still pass after pattern update."""
    violations = []

    for file_path in FILES_TO_CHECK:
        if not file_path.exists():
            violations.append(f"Missing file: {file_path}")
            continue

        content = file_path.read_text()

        if UNCONDITIONAL_OR_PATTERN.search(content):
            violations.append(
                f"{file_path.relative_to(PROJECT_ROOT)}: "
                "Found unconditional 'X OR Y' pattern"
            )

    assert not violations, "\n".join(violations)
