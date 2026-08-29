import os
import sys
from pathlib import Path

from dotenv import load_dotenv

DEFAULT_VAULT = "/Users/kevinbostic/Desktop/JARVIS/Jarvis"
DEFAULT_MODEL = "google/gemini-2.0-flash-001"
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_env() -> None:
    load_dotenv(PROJECT_ROOT / ".env")
    load_dotenv()


def config_error(message: str) -> None:
    print(f"CONFIG ERROR: {message}", file=sys.stderr)
    raise SystemExit(2)


class Config:
    def __init__(self) -> None:
        _load_env()
        vault = os.environ.get("JARVIS_VAULT_PATH", DEFAULT_VAULT).strip()
        self.vault_path = Path(vault).expanduser()
        self.model = os.environ.get("JARVIS_OPEN_MODEL", DEFAULT_MODEL).strip()
        self.openrouter_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
        self.project_root = PROJECT_ROOT
        self._validate()

    def _validate(self) -> None:
        if not self.vault_path.is_dir():
            config_error(
                f"JARVIS_VAULT_PATH is not a directory: {self.vault_path}"
            )
        registry = self.vault_path / "projects" / "registry.md"
        if not registry.is_file():
            config_error(f"Registry not found: {registry}")

    @property
    def registry_path(self) -> Path:
        return self.vault_path / "projects" / "registry.md"

    @property
    def rules_dir(self) -> Path:
        return self.vault_path / ".cursor" / "rules"
