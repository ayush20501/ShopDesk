import os
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _flag(name, default):
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    endpoint: str
    api_key: str
    api_version: str
    deployment: str
    db_path: Path
    chroma_dir: Path
    policies_dir: Path
    store_today: date
    chunking: str = "heading"
    retrieval: str = "hybrid"
    use_checker: bool = True
    top_k: int = 4
    max_rows: int = 30

    def with_(self, **changes):
        return replace(self, **changes)


def _path(name, default):
    p = Path(os.getenv(name) or default)
    return p if p.is_absolute() else ROOT / p


def load_settings():
    return Settings(
        endpoint=os.getenv("AZURE_OPENAI_ENDPOINT", "").strip(),
        api_key=os.getenv("AZURE_OPENAI_API_KEY", "").strip(),
        api_version=os.getenv("AZURE_OPENAI_API_VERSION", "").strip(),
        deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT", "").strip(),
        db_path=_path("DB_PATH", "data/shop.db"),
        chroma_dir=_path("CHROMA_DIR", "data/chroma"),
        policies_dir=_path("POLICIES_DIR", "data/policies"),
        store_today=date.fromisoformat(os.getenv("STORE_TODAY", "2026-11-20")),
        chunking=os.getenv("CHUNKING", "heading").strip().lower(),
        retrieval=os.getenv("RETRIEVAL", "hybrid").strip().lower(),
        use_checker=_flag("USE_CHECKER", True),
        top_k=int(os.getenv("TOP_K", "4")),
    )
