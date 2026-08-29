import subprocess
from pathlib import Path

from jarvis_open.models import ScanMode, ScanResult, ScannedFile

FFOOTBALL_EXCLUDES = {".next", "node_modules"}
OUTREACH_EXCLUDES = {".venv", "drafts", "data"}
L2_FILE_CAP = 30


def _run_git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout


def _resolve_base_branch(repo: Path) -> str | None:
    checks = [
        ["symbolic-ref", "refs/remotes/origin/HEAD"],
        ["rev-parse", "--verify", "refs/remotes/origin/main"],
        ["rev-parse", "--verify", "refs/remotes/origin/master"],
        ["rev-parse", "--verify", "main"],
        ["rev-parse", "--verify", "master"],
    ]
    for cmd in checks:
        result = subprocess.run(
            ["git", *cmd],
            cwd=repo,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            continue
        ref = result.stdout.strip()
        if cmd[0] == "symbolic-ref":
            if ref.startswith("refs/remotes/origin/"):
                return ref.split("/", 3)[-1]
            return ref.replace("refs/remotes/origin/", "")
        if ref.startswith("refs/remotes/origin/"):
            return ref.split("/", 3)[-1]
        return ref
    return None


def _in_scope(slug: str, rel: str) -> bool:
    rel_path = Path(rel)
    parts = rel_path.parts
    if slug == "ffootball":
        if not parts:
            return False
        if parts[0] not in ("src", "scripts"):
            return False
        for p in parts:
            if p in FFOOTBALL_EXCLUDES:
                return False
        return True
    if slug == "outreach":
        if len(parts) != 1 or not rel_path.suffix == ".py":
            return False
        for p in parts:
            if p in OUTREACH_EXCLUDES:
                return False
        return True
    return False


def _filter_paths(slug: str, paths: set[str]) -> list[str]:
    return sorted(p for p in paths if _in_scope(slug, p))


def _collect_diff_mode(repo: Path, slug: str) -> tuple[ScanMode, str, dict[str, int]]:
    """Return mode, mode_note, and path -> priority bucket."""
    base = _resolve_base_branch(repo)
    buckets: dict[str, int] = {}

    if base is None:
        mode = ScanMode.WORKING_TREE_ONLY
        mode_note = "scan mode: working-tree only — base branch could not be resolved"
        unstaged = set(_run_git(repo, "diff", "--name-only").splitlines())
        staged = set(_run_git(repo, "diff", "--cached", "--name-only").splitlines())
        for p in unstaged:
            buckets[p] = 0
        for p in staged:
            if p not in buckets:
                buckets[p] = 1
        return mode, mode_note, buckets

    merge_base = _run_git(repo, "merge-base", base, "HEAD").strip()
    branch = set(
        _run_git(repo, "diff", "--name-only", f"{merge_base}..HEAD").splitlines()
    )
    staged = set(_run_git(repo, "diff", "--cached", "--name-only").splitlines())
    unstaged = set(_run_git(repo, "diff", "--name-only").splitlines())

    for p in unstaged:
        buckets[p] = 0
    for p in staged:
        if p not in buckets:
            buckets[p] = 1
    for p in branch:
        if p not in buckets:
            buckets[p] = 2

    return ScanMode.DIFF, "", buckets


def _collect_uncommitted(repo: Path) -> dict[str, int]:
    paths = set(_run_git(repo, "diff", "HEAD", "--name-only").splitlines())
    return {p: 0 for p in paths}


def _collect_full(repo: Path, slug: str) -> dict[str, int]:
    buckets: dict[str, int] = {}
    root = repo
    if slug == "ffootball":
        for sub in ("src", "scripts"):
            sub_path = root / sub
            if not sub_path.is_dir():
                continue
            for path in sub_path.rglob("*"):
                if not path.is_file():
                    continue
                rel = path.relative_to(root).as_posix()
                if _in_scope(slug, rel):
                    buckets[rel] = 2
    elif slug == "outreach":
        for path in root.glob("*.py"):
            rel = path.relative_to(root).as_posix()
            if _in_scope(slug, rel):
                buckets[rel] = 2
    return buckets


def scan_repo(
    slug: str,
    repo_path: Path,
    mode: str,
    force_l2: bool,
) -> ScanResult:
    if not repo_path.is_dir():
        raise RuntimeError(f"Repo path not found: {repo_path}")
    if not (repo_path / ".git").is_dir():
        raise RuntimeError(f"Not a git repo: {repo_path}")

    mode_note = ""
    if mode == "full":
        scan_mode = ScanMode.FULL
        buckets = _collect_full(repo_path, slug)
    elif mode == "uncommitted":
        scan_mode = ScanMode.UNCOMMITTED
        buckets = _collect_uncommitted(repo_path)
    else:
        scan_mode, mode_note, buckets = _collect_diff_mode(repo_path, slug)

    scoped = _filter_paths(slug, set(buckets.keys()))
    files: list[ScannedFile] = []
    for rel in scoped:
        files.append(
            ScannedFile(
                path=rel,
                priority=buckets.get(rel, 2),
                absolute=str(repo_path / rel),
            )
        )

    files.sort(key=lambda f: (f.priority, f.path))

    skipped_l2: list[str] = []
    if len(files) > L2_FILE_CAP and not force_l2:
        skipped_l2 = [f.path for f in files[L2_FILE_CAP:]]
        files = files[:L2_FILE_CAP]

    return ScanResult(
        repo_slug=slug,
        repo_path=str(repo_path),
        mode=scan_mode,
        mode_note=mode_note,
        files=files,
        skipped_l2_paths=skipped_l2,
    )


def file_diff(repo: Path, rel_path: str, base_branch: str | None) -> str:
    """Unified diff for a file, or empty if unavailable."""
    try:
        unstaged = _run_git(repo, "diff", "--", rel_path)
        staged = _run_git(repo, "diff", "--cached", "--", rel_path)
        parts = []
        if unstaged:
            parts.append(unstaged)
        if staged:
            parts.append(staged)
        if parts:
            return "\n".join(parts)
        if base_branch:
            merge_base = _run_git(repo, "merge-base", base_branch, "HEAD").strip()
            branch_diff = _run_git(repo, "diff", f"{merge_base}..HEAD", "--", rel_path)
            return branch_diff
    except RuntimeError:
        return ""
    return ""


def get_base_branch(repo: Path) -> str | None:
    return _resolve_base_branch(repo)
