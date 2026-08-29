import json
import re
from datetime import date, datetime
from pathlib import Path

from jarvis_open.models import Finding, ScanMode, ScanResult, Verdict


def format_location(f: Finding) -> str:
    if f.line > 0:
        return f"{f.path}:{f.line}"
    return f.path


def print_table(findings: list[Finding]) -> None:
    if not findings:
        print("No findings.")
        return
    print("| Repo | Rule | Verdict | Location | Reason |")
    print("|------|------|---------|----------|--------|")
    for f in findings:
        loc = format_location(f)
        reason = f.reason.replace("|", "\\|")
        print(f"| {f.repo} | {f.rule_id} | {f.verdict.value} | {loc} | {reason} |")


def write_json_report(findings: list[Finding], reports_dir: Path) -> Path:
    reports_dir.mkdir(parents=True, exist_ok=True)
    out = reports_dir / "last_check.json"
    data = [
        {
            "repo": f.repo,
            "rule_id": f.rule_id,
            "verdict": f.verdict.value,
            "path": f.path,
            "line": f.line,
            "reason": f.reason,
            "layer": f.layer,
            "pattern_name": f.pattern_name,
        }
        for f in findings
    ]
    out.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return out


def has_failures(findings: list[Finding]) -> bool:
    return any(f.verdict == Verdict.FAIL for f in findings)


def _count_by_repo_rule(findings: list[Finding]) -> dict[str, dict[str, int]]:
    counts: dict[str, dict[str, int]] = {}
    for f in findings:
        counts.setdefault(f.repo, {})
        counts[f.repo][f.rule_id] = counts[f.repo].get(f.rule_id, 0) + 1
    return counts


def write_vault_outputs(
    vault_path: Path,
    findings: list[Finding],
    scan_results: list[ScanResult],
    layers_run: str,
    warnings: list[str],
) -> Path:
    today = date.today().isoformat()
    out_dir = vault_path / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{today}-jarvis-open.md"

    lines: list[str] = [
        f"# Jarvis Open report — {today}",
        "",
        f"**Timestamp:** {datetime.now().isoformat(timespec='seconds')}",
        f"**Layers run:** {layers_run}",
        "",
    ]

    for sr in scan_results:
        mode_str = sr.mode.value if isinstance(sr.mode, ScanMode) else str(sr.mode)
        lines.append(f"- **{sr.repo_slug}** scan mode: `{mode_str}`")
        if sr.mode_note:
            lines.append(f"  - {sr.mode_note}")
        if sr.skipped_l2_paths:
            lines.append(
                f"  - Layer 2 skipped on {len(sr.skipped_l2_paths)} files (>30 cap)"
            )

    if warnings:
        lines.append("")
        lines.append("## Warnings")
        for w in warnings:
            lines.append(f"- {w}")

    lines.append("")
    lines.append("## Summary counts")
    counts = _count_by_repo_rule(findings)
    for repo, rules in sorted(counts.items()):
        for rule_id, n in sorted(rules.items()):
            lines.append(f"- {repo} / {rule_id}: {n}")

    lines.append("")
    lines.append("## Findings")
    if not findings:
        lines.append("No findings.")
    else:
        lines.append("| Repo | Rule | Verdict | Location | Reason |")
        lines.append("|------|------|---------|----------|--------|")
        for f in findings:
            loc = format_location(f)
            reason = f.reason.replace("|", "\\|")
            lines.append(
                f"| {f.repo} | {f.rule_id} | {f.verdict.value} | {loc} | {reason} |"
            )

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_path


def _review_key(f: Finding) -> tuple[str, str, int, str]:
    return (f.repo, f.path, f.line, f.rule_id)


def _parse_review_items(section_text: str) -> dict[tuple[str, str, int, str], str]:
    items: dict[tuple[str, str, int, str], str] = {}
    for line in section_text.splitlines():
        m = re.match(
            r"^- \[ \] (.+?) — (.+)$",
            line.strip(),
        )
        if not m:
            continue
        # Keys stored in line text; we rebuild from findings when merging
        items[(line, m.group(2))] = line
    return items


def write_vault_review(
    vault_path: Path,
    findings: list[Finding],
) -> None:
    """Append review items for safety fails and playbook 01/02 layer 2 fails."""
    today = date.today().isoformat()
    review_dir = vault_path / "review"
    review_dir.mkdir(parents=True, exist_ok=True)
    review_path = review_dir / f"{today}-projects.md"

    review_findings: list[Finding] = []
    for f in findings:
        if f.verdict != Verdict.FAIL:
            continue
        if f.rule_id == "safety":
            review_findings.append(f)
        elif f.layer == 2 and f.rule_id in (
            "agent-workflow",
            "simplicity-and-teaching",
            "simplicity-01",
            "simplicity-02",
        ):
            review_findings.append(f)

    if not review_findings:
        return

    section_header = "## Jarvis Open"
    existing = ""
    if review_path.is_file():
        existing = review_path.read_text(encoding="utf-8")

    # Parse existing keys from section
    existing_keys: set[tuple[str, str, int, str]] = set()
    if section_header in existing:
        section = existing.split(section_header, 1)[1]
        for line in section.splitlines():
            for f in review_findings:
                loc = format_location(f)
                if loc in line and f.rule_id in line:
                    existing_keys.add(_review_key(f))

    new_lines: list[str] = []
    for f in review_findings:
        key = _review_key(f)
        if key in existing_keys:
            continue
        loc = format_location(f)
        if f.rule_id == "safety":
            pat = f.pattern_name or "credential"
            text = f"Rotate/remove credential at `{loc}` (pattern: {pat})"
        else:
            text = f"{f.reason} — `{loc}`"
        new_lines.append(f"- [ ] **Approve** / [ ] **Reject** — {text}")

    if not new_lines:
        return

    if not review_path.is_file():
        content = f"# Project review — {today}\n\n{section_header}\n\n"
        content += "\n".join(new_lines) + "\n"
        review_path.write_text(content, encoding="utf-8")
        return

    if section_header in existing:
        updated = existing.rstrip() + "\n" + "\n".join(new_lines) + "\n"
    else:
        updated = existing.rstrip() + f"\n\n{section_header}\n\n" + "\n".join(new_lines) + "\n"
    review_path.write_text(updated, encoding="utf-8")


def write_vault_log(vault_path: Path, finding_count: int) -> None:
    today = date.today().isoformat()
    log_path = vault_path / "log.md"
    entry = f"## [{today}] improve | Jarvis Open — {finding_count} findings"
    if not log_path.is_file():
        log_path.write_text(entry + "\n", encoding="utf-8")
        return
    content = log_path.read_text(encoding="utf-8")
    if entry in content:
        # Update count on same-day re-run
        lines = content.splitlines()
        new_lines = []
        for line in lines:
            if line.startswith(f"## [{today}] improve | Jarvis Open"):
                new_lines.append(entry)
            else:
                new_lines.append(line)
        log_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    else:
        log_path.write_text(content.rstrip() + "\n" + entry + "\n", encoding="utf-8")
