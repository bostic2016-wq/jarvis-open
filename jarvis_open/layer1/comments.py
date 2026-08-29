import re
from pathlib import Path

from jarvis_open.models import Finding, Verdict

NARRATION_RE = re.compile(
    r"^\s*(?:#|//)\s*(import|return|define|create|initialize|set|get|call|loop|iterate)\b",
    re.IGNORECASE,
)

# Business-logic phrases that should not match narration heuristics
BUSINESS_LOGIC_HINTS = re.compile(
    r"return_exceptions|rate.?limit|edge case|business|because|if the|when the|so that",
    re.IGNORECASE,
)


def scan_file_comments(repo_slug: str, rel_path: str, abs_path: Path) -> list[Finding]:
    if not abs_path.is_file():
        return []
    try:
        lines = abs_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []

    findings: list[Finding] = []
    for line_no, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped.startswith("#") and not stripped.startswith("//"):
            continue
        if BUSINESS_LOGIC_HINTS.search(line):
            continue
        if NARRATION_RE.match(line):
            findings.append(
                Finding(
                    repo=repo_slug,
                    rule_id="simplicity-02",
                    verdict=Verdict.FAIL,
                    path=rel_path,
                    line=line_no,
                    reason="Narration comment (explains syntax, not business logic)",
                    layer=1,
                )
            )
    return findings
