from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Verdict(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"
    UNCERTAIN = "uncertain"


class ScanMode(str, Enum):
    DIFF = "diff"
    FULL = "full"
    UNCOMMITTED = "uncommitted"
    WORKING_TREE_ONLY = "working-tree only — base branch could not be resolved"


@dataclass
class Finding:
    repo: str
    rule_id: str
    verdict: Verdict
    path: str
    line: int
    reason: str
    layer: int = 1
    pattern_name: Optional[str] = None


@dataclass
class ScannedFile:
    path: str  # relative to repo root
    priority: int  # 0=uncommitted, 1=staged, 2=branch-committed
    absolute: str


@dataclass
class ScanResult:
    repo_slug: str
    repo_path: str
    mode: ScanMode
    mode_note: str = ""
    files: list[ScannedFile] = field(default_factory=list)
    skipped_l2_paths: list[str] = field(default_factory=list)
