"""Application configuration, loaded from environment / .env."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for Paperfin.

    Values can be overridden with environment variables or a local ``.env`` file
    sitting next to ``pyproject.toml``.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- LLM (Anthropic-compatible) --------------------------------------
    # Point ``anthropic_base_url`` at a compatible gateway (e.g. MiniMax at
    # https://api.minimaxi.com/anthropic) or leave empty to hit the official
    # Anthropic API.
    anthropic_api_key: str = ""
    anthropic_base_url: str = ""
    anthropic_model: str = "claude-opus-4-7"

    # Language the LLM uses for summaries and scoring rationales. Two values
    # ship in the box — "en" (default) and "zh" (Simplified Chinese); adding a
    # new language means adding one more prompt block in
    # ``app/services/summarizer.py`` and ``app/services/quality.py``.
    summary_language: str = "en"

    # --- External APIs ---------------------------------------------------
    semantic_scholar_api_key: str = ""

    # --- Runtime paths ---------------------------------------------------
    data_dir: Path = Path("./data")
    scan_interval_hours: int = 6

    log_level: str = "INFO"

    # ---------------------------------------------------------------------
    @property
    def papers_dir(self) -> Path:
        return self.data_dir / "papers"

    @property
    def thumbnails_dir(self) -> Path:
        return self.data_dir / "thumbnails"

    @property
    def sqlite_path(self) -> Path:
        return self.data_dir / "paperfin.db"

    @property
    def sqlite_url(self) -> str:
        return f"sqlite:///{self.sqlite_path.resolve()}"

    def ensure_dirs(self) -> None:
        """Create runtime directories if they do not exist yet."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.papers_dir.mkdir(parents=True, exist_ok=True)
        self.thumbnails_dir.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
