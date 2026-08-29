import json
import re
from datetime import datetime
from pathlib import Path

import httpx

from jarvis_open.config import Config
from jarvis_open.models import Finding, Verdict
from jarvis_open.rules import Rule, rules_system_text
from jarvis_open.scan import file_diff, get_base_branch

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MAX_PROMPT_CHARS = 12000
CONTEXT_SNIPPET_CHARS = 500


def _strip_json_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _truncate_diff(diff: str, max_chars: int = MAX_PROMPT_CHARS) -> str:
    if len(diff) <= max_chars:
        return diff
    return diff[:max_chars] + "\n... [truncated]"


def _build_user_prompt(
    repo_path: Path,
    rel_path: str,
    scan_mode: str,
    base_branch: str | None,
) -> str:
    abs_path = repo_path / rel_path
    parts = [f"File: {rel_path}"]

    if scan_mode in ("diff", "working-tree only — base branch could not be resolved"):
        diff = file_diff(repo_path, rel_path, base_branch)
        if diff:
            parts.append("Unified diff:")
            parts.append(_truncate_diff(diff))
            return "\n\n".join(parts)
    if abs_path.is_file():
        try:
            body = abs_path.read_text(encoding="utf-8", errors="replace")
            if len(body) > MAX_PROMPT_CHARS:
                body = body[:MAX_PROMPT_CHARS] + "\n... [truncated]"
            parts.append("File content:")
            parts.append(body)
        except OSError:
            parts.append("(could not read file)")
    return "\n\n".join(parts)


def eval_gate_passes(project_root: Path, vault_path: Path, skip_gate: bool) -> tuple[bool, str]:
    if skip_gate:
        return True, ""
    last_run = project_root / "evals" / "last_run.json"
    if not last_run.is_file():
        return False, "Layer 2 skipped: no evals/last_run.json — run python evals/run_evals.py first"

    try:
        data = json.loads(last_run.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False, "Layer 2 skipped: evals/last_run.json is invalid"

    if not data.get("layer1_pass") or not data.get("layer2_pass"):
        return False, "Layer 2 skipped: last eval run did not meet thresholds"

    if data.get("eval_mode") != "openrouter":
        return False, "Layer 2 skipped: evals must be run with OPENROUTER_API_KEY (openrouter mode)"

    run_ts = data.get("timestamp", "")
    try:
        run_time = datetime.fromisoformat(run_ts)
    except (TypeError, ValueError):
        return False, "Layer 2 skipped: eval timestamp missing or invalid"

    stale_files: list[Path] = []
    patterns = [
        project_root / "jarvis_open" / "layer2" / "judge.py",
        project_root / "evals" / "rubric.md",
        project_root / "jarvis_open" / "layer1",
        project_root / "evals" / "fixtures",
        vault_path / ".cursor" / "rules" / "agent-workflow.mdc",
        vault_path / ".cursor" / "rules" / "simplicity-and-teaching.mdc",
    ]
    for p in patterns:
        if p.is_file():
            mtime = datetime.fromtimestamp(p.stat().st_mtime)
            if mtime > run_time:
                stale_files.append(p)
        elif p.is_dir():
            for f in p.rglob("*"):
                if f.is_file():
                    mtime = datetime.fromtimestamp(f.stat().st_mtime)
                    if mtime > run_time:
                        stale_files.append(f)
                        break

    if stale_files:
        return False, (
            "Layer 2 skipped: eval results stale (source files changed since last eval). "
            "Re-run python evals/run_evals.py"
        )
    return True, ""


def judge_file(
    config: Config,
    rules: list[Rule],
    rubric_path: Path,
    repo_slug: str,
    repo_path: Path,
    rel_path: str,
    scan_mode: str,
) -> list[Finding]:
    rubric = rubric_path.read_text(encoding="utf-8")
    system = (
        "You are a code playbook compliance judge. Respond with JSON only, no markdown.\n\n"
        f"## Rubric\n{rubric}\n\n"
        f"{rules_system_text(rules)}\n\n"
        "Response schema: {\"rule_id\": \"agent-workflow|simplicity-and-teaching|simplicity-01|simplicity-02\", "
        "\"verdict\": \"pass|fail|uncertain\", \"lines\": [42], \"reason\": \"...\"}"
    )
    base = get_base_branch(repo_path)
    user = _build_user_prompt(repo_path, rel_path, scan_mode, base)

    headers = {
        "Authorization": f"Bearer {config.openrouter_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost",
        "X-Title": "jarvis-open",
    }
    body = {
        "model": config.model,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }

    with httpx.Client(timeout=120.0) as client:
        resp = client.post(OPENROUTER_URL, headers=headers, json=body)
        if resp.status_code != 200:
            raise RuntimeError(f"OpenRouter error {resp.status_code}: {resp.text[:240]}")
        data = resp.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")

    for attempt in range(2):
        try:
            parsed = json.loads(_strip_json_fences(content))
            break
        except json.JSONDecodeError:
            if attempt == 0:
                continue
            return [
                Finding(
                    repo=repo_slug,
                    rule_id="agent-workflow",
                    verdict=Verdict.UNCERTAIN,
                    path=rel_path,
                    line=0,
                    reason="Judge returned unparseable JSON",
                    layer=2,
                )
            ]

    verdict_str = str(parsed.get("verdict", "uncertain")).lower()
    if verdict_str == "pass":
        verdict = Verdict.PASS
    elif verdict_str == "fail":
        verdict = Verdict.FAIL
    else:
        verdict = Verdict.UNCERTAIN

    rule_id = str(parsed.get("rule_id", "agent-workflow"))
    reason = str(parsed.get("reason", "Layer 2 judgment"))
    lines = parsed.get("lines") or []
    line_no = int(lines[0]) if lines else 0

    if verdict == Verdict.PASS:
        return []

    return [
        Finding(
            repo=repo_slug,
            rule_id=rule_id,
            verdict=verdict,
            path=rel_path,
            line=line_no,
            reason=reason,
            layer=2,
        )
    ]
