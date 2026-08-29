import re
import sys
from dataclasses import dataclass
from pathlib import Path

from jarvis_open.config import config_error


@dataclass
class RepoEntry:
    slug: str
    name: str
    path: Path


SLUG_PATTERNS = {
    "ffootball": ["ffootball", "fantasy football"],
    "outreach": ["outreach"],
}


def _parse_table_rows(registry_text: str) -> list[dict[str, str]]:
    lines = registry_text.splitlines()
    header_idx = None
    headers: list[str] = []
    for i, line in enumerate(lines):
        if line.strip().startswith("|") and "Status" in line and "Path" in line:
            header_idx = i
            headers = [h.strip().lower() for h in line.strip().strip("|").split("|")]
            break
    if header_idx is None:
        config_error("Could not parse registry.md table header")

    rows: list[dict[str, str]] = []
    for line in lines[header_idx + 2:]:
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < len(headers):
            continue
        row = {headers[j]: cells[j] for j in range(len(headers))}
        rows.append(row)
    return rows


def _slug_for_name(name: str) -> str | None:
    lower = name.lower()
    for slug, patterns in SLUG_PATTERNS.items():
        for pat in patterns:
            if pat in lower:
                return slug
    return None


def load_active_repos(registry_path: Path, slug_filter: str | None = None) -> list[RepoEntry]:
    text = registry_path.read_text(encoding="utf-8")
    rows = _parse_table_rows(text)
    entries: list[RepoEntry] = []

    for row in rows:
        status = row.get("status", "").lower()
        if status != "active":
            continue
        path_raw = row.get("path", "").strip()
        if not path_raw.startswith("/"):
            continue
        name = row.get("name", "").strip()
        slug = _slug_for_name(name)
        if slug is None:
            continue
        if slug_filter and slug != slug_filter:
            continue
        path = Path(path_raw)
        entries.append(RepoEntry(slug=slug, name=name, path=path))

    if slug_filter:
        matches = [e for e in entries if e.slug == slug_filter]
        if len(matches) == 0:
            print(
                f"CONFIG ERROR: unknown or inactive repo: {slug_filter}",
                file=sys.stderr,
            )
            raise SystemExit(2)
        if len(matches) > 1:
            print(
                f"CONFIG ERROR: ambiguous repo slug: {slug_filter}",
                file=sys.stderr,
            )
            raise SystemExit(2)
        return matches

    # Default: only ffootball and outreach slugs
    by_slug: dict[str, RepoEntry] = {}
    for e in entries:
        if e.slug in SLUG_PATTERNS:
            if e.slug in by_slug:
                print(
                    f"CONFIG ERROR: ambiguous repo slug: {e.slug}",
                    file=sys.stderr,
                )
                raise SystemExit(2)
            by_slug[e.slug] = e
    return [by_slug[s] for s in ("ffootball", "outreach") if s in by_slug]

