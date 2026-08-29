import argparse
import sys
from pathlib import Path

from jarvis_open.config import Config
from jarvis_open.layer1.comments import scan_file_comments
from jarvis_open.layer1.secrets import check_tracked_env, scan_file_secrets
from jarvis_open.layer1.size import scan_file_size
from jarvis_open.layer2.judge import eval_gate_passes, judge_file
from jarvis_open.models import Finding, ScanMode, Verdict
from jarvis_open.registry import load_active_repos
from jarvis_open.report import (
    has_failures,
    print_table,
    write_json_report,
    write_vault_log,
    write_vault_outputs,
    write_vault_review,
)
from jarvis_open.rules import load_rules
from jarvis_open.scan import scan_repo


def run_layer1(
    config: Config,
    repo_slug: str,
    repo_path: Path,
    files: list,
) -> list[Finding]:
    findings: list[Finding] = []
    findings.extend(check_tracked_env(repo_path, repo_slug))
    for sf in files:
        rel = sf.path
        abs_path = Path(sf.absolute)
        findings.extend(
            scan_file_secrets(repo_path, repo_slug, rel, config.project_root)
        )
        findings.extend(scan_file_comments(repo_slug, rel, abs_path))
        findings.extend(scan_file_size(repo_slug, rel, abs_path))
    return findings


def file_has_layer1_fail(findings: list[Finding], rel_path: str) -> bool:
    return any(
        f.path == rel_path and f.layer == 1 and f.verdict == Verdict.FAIL
        for f in findings
    )


def file_has_size_warn(findings: list[Finding], rel_path: str) -> bool:
    return any(
        f.path == rel_path
        and f.layer == 1
        and f.rule_id == "simplicity-01"
        and f.verdict == Verdict.WARN
        for f in findings
    )


def run_check(args: argparse.Namespace) -> int:
    config = Config()
    repos = load_active_repos(config.registry_path, args.repo)
    rules = load_rules(config.rules_dir)
    rubric_path = config.project_root / "evals" / "rubric.md"

    scan_mode_arg = "full" if args.full else "uncommitted" if args.uncommitted else "diff"
    layer = args.layer
    if layer == "all":
        run_l1 = True
        run_l2 = True
    elif layer == "1":
        run_l1 = True
        run_l2 = False
    else:
        run_l1 = False
        run_l2 = True

    warnings: list[str] = []
    all_findings: list[Finding] = []
    scan_results = []

    gate_ok = True
    gate_msg = ""
    if run_l2:
        if not config.openrouter_key:
            run_l2 = False
            warnings.append(
                "Layer 2 skipped: OPENROUTER_API_KEY not set (Layer 1 completed)"
            )
        else:
            gate_ok, gate_msg = eval_gate_passes(
                config.project_root, config.vault_path, args.skip_eval_gate
            )
            if not gate_ok:
                run_l2 = False
                warnings.append(gate_msg)

    for repo in repos:
        if not repo.path.is_dir():
            print(f"CONFIG ERROR: repo path not found: {repo.path}", file=sys.stderr)
            return 2
        try:
            sr = scan_repo(
                repo.slug,
                repo.path,
                scan_mode_arg,
                args.force,
            )
        except RuntimeError as e:
            print(f"RUNTIME ERROR: {e}", file=sys.stderr)
            return 2
        scan_results.append(sr)

        if sr.skipped_l2_paths:
            warnings.append(
                f"{repo.slug}: Layer 2 skipped on {len(sr.skipped_l2_paths)} files "
                f"(>30 cap, use --force to judge all)"
            )

        l1_findings: list[Finding] = []
        if run_l1 or run_l2:
            l1_findings = run_layer1(config, repo.slug, repo.path, sr.files)
            if run_l1:
                all_findings.extend(l1_findings)

        if run_l2 and config.openrouter_key and gate_ok:
            mode_str = sr.mode.value
            for sf in sr.files:
                if file_has_layer1_fail(l1_findings, sf.path):
                    continue
                if sr.mode == ScanMode.FULL and file_has_size_warn(
                    l1_findings, sf.path
                ):
                    if not args.force:
                        continue
                try:
                    l2 = judge_file(
                        config,
                        rules,
                        rubric_path,
                        repo.slug,
                        repo.path,
                        sf.path,
                        mode_str,
                    )
                    all_findings.extend(l2)
                except Exception as e:
                    warnings.append(f"Layer 2 error on {sf.path}: {e}")

    layers_run = []
    if run_l1:
        layers_run.append("1")
    if run_l2:
        layers_run.append("2")
    layers_label = ",".join(layers_run) if layers_run else "none"

    print_table(all_findings)
    write_json_report(all_findings, config.project_root / "reports")

    if warnings:
        print("\nWarnings:")
        for w in warnings:
            print(f"  - {w}")

    if args.write_vault:
        out = write_vault_outputs(
            config.vault_path,
            all_findings,
            scan_results,
            layers_label,
            warnings,
        )
        write_vault_review(config.vault_path, all_findings)
        write_vault_log(config.vault_path, len(all_findings))
        print(f"\nVault report: {out}")

    if has_failures(all_findings):
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="jarvis_open", description="Jarvis Open playbook checker")
    sub = p.add_subparsers(dest="command")

    check = sub.add_parser("check", help="Run compliance check")
    check.add_argument("--repo", choices=["ffootball", "outreach"])
    check.add_argument("--layer", default="all", choices=["1", "2", "all"])
    check.add_argument("--full", action="store_true")
    check.add_argument("--uncommitted", action="store_true")
    check.add_argument("--force", action="store_true", help="Judge all files / override caps")
    check.add_argument("--write-vault", action="store_true")
    check.add_argument("--skip-eval-gate", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command != "check":
        parser.print_help()
        return 2
    return run_check(args)
