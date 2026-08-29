import re
import subprocess
from pathlib import Path

from jarvis_open.models import Finding, Verdict

SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("openai_sk", re.compile(r"sk-[a-zA-Z0-9]{20,}")),
    ("bearer_token", re.compile(r"Bearer\s+[a-zA-Z0-9._\-]{20,}")),
    ("pem_private_key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    (
        "api_key_assignment",
        re.compile(
            r"(?:API_KEY|api_key|SECRET_KEY|secret_key)\s*[=:]\s*['\"]?[a-zA-Z0-9_\-]{8,}",
            re.IGNORECASE,
        ),
    ),
    ("generic_api_key", re.compile(r"(?:api[_-]?key)\s*[=:]\s*['\"][^'\"]{8,}['\"]", re.IGNORECASE)),
]

TEST_FILE_RE = re.compile(
    r"(?:\.test\.(ts|tsx|js|jsx)$|_test\.py$|^test_.*\.py$)",
    re.IGNORECASE,
)

EXAMPLE_BASENAMES = {".env.example", ".env.local.example"}


def _git_check_ignore(repo: Path, rel_path: str) -> bool:
    result = subprocess.run(
        ["git", "check-ignore", "-q", rel_path],
        cwd=repo,
        capture_output=True,
    )
    return result.returncode == 0


def _is_test_file(rel_path: str) -> bool:
    basename = Path(rel_path).name
    return bool(TEST_FILE_RE.search(basename))


def _is_fixture_path(rel_path: str, project_root: Path) -> bool:
    norm = rel_path.replace("\\", "/")
    if "evals/fixtures/" in norm:
        return True
    return False


def _is_example_env(rel_path: str) -> bool:
    name = Path(rel_path).name
    if name in EXAMPLE_BASENAMES:
        return True
    return name.endswith(".env.example")


def _downgrade_eligible(repo: Path, rel_path: str, project_root: Path) -> bool:
    if _is_test_file(rel_path):
        return False
    if _is_example_env(rel_path):
        return True
    if _is_fixture_path(rel_path, project_root):
        return True
    if _git_check_ignore(repo, rel_path):
        return True
    return False


def check_tracked_env(repo: Path, repo_slug: str) -> list[Finding]:
    result = subprocess.run(
        ["git", "ls-files", ".env"],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    findings: list[Finding] = []
    if result.returncode != 0:
        return findings
    for line in result.stdout.splitlines():
        p = line.strip()
        if p:
            findings.append(
                Finding(
                    repo=repo_slug,
                    rule_id="safety",
                    verdict=Verdict.FAIL,
                    path=p,
                    line=0,
                    reason="Tracked .env file in git",
                    layer=1,
                    pattern_name="tracked_env",
                )
            )
    return findings


def scan_file_secrets(
    repo: Path,
    repo_slug: str,
    rel_path: str,
    project_root: Path,
) -> list[Finding]:
    abs_path = repo / rel_path
    if not abs_path.is_file():
        return []
    try:
        text = abs_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    findings: list[Finding] = []
    is_test = _is_test_file(rel_path)

    for line_no, line in enumerate(text.splitlines(), start=1):
        for pattern_name, pattern in SECRET_PATTERNS:
            if not pattern.search(line):
                continue
            verdict = Verdict.FAIL
            reason = f"Credential pattern detected ({pattern_name})"
            if not is_test and _downgrade_eligible(repo, rel_path, project_root):
                verdict = Verdict.WARN
                reason = f"Credential-like pattern ({pattern_name}) in ignored/example path"
            findings.append(
                Finding(
                    repo=repo_slug,
                    rule_id="safety",
                    verdict=verdict,
                    path=rel_path,
                    line=line_no,
                    reason=reason,
                    layer=1,
                    pattern_name=pattern_name,
                )
            )
    return findings
