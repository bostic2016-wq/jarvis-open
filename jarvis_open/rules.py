import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Rule:
    rule_id: str
    body: str


FRONTMATTER_RE = re.compile(r"^---\s*\n.*?\n---\s*\n", re.DOTALL)


def _strip_frontmatter(text: str) -> str:
    return FRONTMATTER_RE.sub("", text, count=1).strip()


def load_rules(rules_dir: Path) -> list[Rule]:
    mapping = {
        "agent-workflow": "agent-workflow.mdc",
        "simplicity-and-teaching": "simplicity-and-teaching.mdc",
    }
    rules: list[Rule] = []
    for rule_id, filename in mapping.items():
        path = rules_dir / filename
        if not path.is_file():
            from jarvis_open.config import config_error

            config_error(f"Rule file not found: {path}")
        body = _strip_frontmatter(path.read_text(encoding="utf-8"))
        rules.append(Rule(rule_id=rule_id, body=body))
    return rules


def rules_system_text(rules: list[Rule]) -> str:
    parts = []
    for r in rules:
        parts.append(f"## Rule: {r.rule_id}\n\n{r.body}")
    return "\n\n".join(parts)
