from pathlib import Path

from jarvis_open.models import Finding, Verdict

MAX_LINES = 400


def scan_file_size(repo_slug: str, rel_path: str, abs_path: Path) -> list[Finding]:
    if not abs_path.is_file():
        return []
    try:
        count = sum(1 for _ in abs_path.open(encoding="utf-8", errors="replace"))
    except OSError:
        return []
    if count > MAX_LINES:
        return [
            Finding(
                repo=repo_slug,
                rule_id="simplicity-01",
                verdict=Verdict.WARN,
                path=rel_path,
                line=0,
                reason=f"Source file exceeds {MAX_LINES} lines ({count} lines)",
                layer=1,
            )
        ]
    return []
