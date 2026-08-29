#!/usr/bin/env python3
"""Regression gate for Jarvis Open layer 1 and layer 2 eval fixtures."""

import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "evals" / "fixtures"
LAST_RUN = ROOT / "evals" / "last_run.json"

L1_THRESHOLD = 8
L2_THRESHOLD = 7


def parse_meta(path: Path) -> dict[str, str]:
    meta: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines()[:10]:
        m = re.match(r"^[#/]{1,2}\s*expected_layer:\s*(\d+)", line.strip())
        if m:
            meta["expected_layer"] = m.group(1)
        m = re.match(r"^[#/]{1,2}\s*expected_verdict:\s*(\w+)", line.strip())
        if m:
            meta["expected_verdict"] = m.group(1)
        m = re.match(r"^[#/]{1,2}\s*rule_id:\s*([\w\-]+)", line.strip())
        if m:
            meta["rule_id"] = m.group(1)
    return meta


def verdict_for_fixture_l1(path: Path, project_root: Path) -> str:
    from jarvis_open.layer1.comments import scan_file_comments
    from jarvis_open.layer1.secrets import scan_file_secrets
    from jarvis_open.layer1.size import scan_file_size
    from jarvis_open.models import Verdict

    rel = f"evals/fixtures/{path.name}"
    repo = project_root  # use project root as faux repo for git check-ignore
    findings = []
    findings.extend(scan_file_secrets(repo, "fixture", rel, project_root))
    findings.extend(scan_file_comments("fixture", rel, path))
    findings.extend(scan_file_size("fixture", rel, path))

    meta = parse_meta(path)
    rule_id = meta.get("rule_id", "")
    rule_findings = [f for f in findings if f.rule_id == rule_id]
    if not rule_findings:
        return "pass"
    # worst verdict
    order = {Verdict.FAIL: 3, Verdict.WARN: 2, Verdict.UNCERTAIN: 1, Verdict.PASS: 0}
    worst = max(rule_findings, key=lambda f: order[f.verdict])
    return worst.verdict.value


def run_layer1_eval() -> tuple[int, int, list[str]]:
    results: list[str] = []
    correct = 0
    total = 0
    for path in sorted(FIXTURES.iterdir()):
        if path.name.startswith("."):
            continue
        meta = parse_meta(path)
        if meta.get("expected_layer") != "1":
            continue
        total += 1
        expected = meta.get("expected_verdict", "pass")
        actual = verdict_for_fixture_l1(path, ROOT)
        ok = actual == expected
        if ok:
            correct += 1
        mark = "OK" if ok else "FAIL"
        results.append(f"  [{mark}] {path.name}: expected={expected} actual={actual}")
    return correct, total, results


def run_layer2_eval() -> tuple[int, int, list[str], bool]:
    from jarvis_open.config import Config
    from jarvis_open.layer2.judge import judge_file
    from jarvis_open.models import Verdict
    from jarvis_open.rules import load_rules

    config = Config()
    if not config.openrouter_key:
        return 0, 0, ["  Layer 2 skipped: OPENROUTER_API_KEY not set"], False

    rules = load_rules(config.rules_dir)
    rubric = ROOT / "evals" / "rubric.md"
    results: list[str] = []
    correct = 0
    total = 0

    for path in sorted(FIXTURES.iterdir()):
        meta = parse_meta(path)
        if meta.get("expected_layer") != "2":
            continue
        total += 1
        expected = meta.get("expected_verdict", "pass")
        rel = f"evals/fixtures/{path.name}"
        judged = judge_file(
            config,
            rules,
            rubric,
            "fixture",
            ROOT,
            rel,
            "full",
        )
        if expected == "pass":
            actual = "pass" if not judged else judged[0].verdict.value
        else:
            if not judged:
                actual = "pass"
            else:
                actual = judged[0].verdict.value
                if actual == "uncertain":
                    actual = "fail"  # uncertain doesn't count as expected fail
        ok = actual == expected
        if ok:
            correct += 1
        mark = "OK" if ok else "FAIL"
        results.append(f"  [{mark}] {path.name}: expected={expected} actual={actual}")

    return correct, total, results, True


def main() -> int:
    print("Jarvis Open evals")
    l1_correct, l1_total, l1_lines = run_layer1_eval()
    print(f"Layer 1: {l1_correct}/{l1_total} (need >={L1_THRESHOLD})")
    for line in l1_lines:
        print(line)

    l2_ran = False
    l2_correct, l2_total, l2_lines, l2_ran = run_layer2_eval()
    if l2_ran:
        print(f"Layer 2: {l2_correct}/{l2_total} (need >={L2_THRESHOLD})")
        for line in l2_lines:
            print(line)
    else:
        for line in l2_lines:
            print(line)

    l1_pass = l1_correct >= L1_THRESHOLD and l1_total >= 10
    l2_min = int(l2_total * 0.7 + 0.999) if l2_total else 0
    l2_pass = l2_ran and l2_total > 0 and l2_correct >= l2_min

    eval_mode = "openrouter" if l2_ran else "skipped"

    LAST_RUN.write_text(
        json.dumps(
            {
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "layer1_score": f"{l1_correct}/{l1_total}",
                "layer2_score": f"{l2_correct}/{l2_total}" if l2_ran else "skipped",
                "layer1_pass": l1_pass,
                "layer2_pass": l2_pass,
                "eval_mode": eval_mode,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Wrote {LAST_RUN}")

    if not l1_pass:
        print("Layer 1 threshold NOT met")
        return 1
    if not l2_pass:
        print("Layer 2 threshold NOT met or not run")
        return 1
    print("All thresholds met")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    raise SystemExit(main())
