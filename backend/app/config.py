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

    # --- LLM provider ----------------------------------------------------
    # Two wire protocols are supported out of the box:
    #   * "anthropic" — Claude, Amazon Bedrock Claude, MiniMax's Anthropic
    #                   endpoint, LiteLLM, or anything else that serves the
    #                   Anthropic Messages API (POST /v1/messages).
    #   * "openai"    — OpenAI itself, DeepSeek, Zhipu, Ollama, vLLM, Groq,
    #                   and any other server exposing Chat Completions
    #                   (POST /v1/chat/completions).
    # The common fields below are used by whichever provider you pick;
    # unused ones are just ignored.
    llm_provider: str = "anthropic"
    llm_api_key: str = ""
    llm_base_url: str = ""      # empty → SDK default (api.anthropic.com / api.openai.com)
    llm_model: str = "claude-opus-4-7"

    # --- Back-compat aliases --------------------------------------------
    # Legacy .env files that only set ANTHROPIC_* still work; we map them
    # onto the generic names if the new ones are blank.
    anthropic_api_key: str = ""
    anthropic_base_url: str = ""
    anthropic_model: str = ""

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

    # ---------------------------------------------------------------------
    # Resolved LLM credentials. We prefer the new generic ``llm_*`` fields
    # but fall back to the legacy ``anthropic_*`` ones so existing .env
    # files keep working without edits.

    @property
    def resolved_llm_api_key(self) -> str:
        return self.llm_api_key or self.anthropic_api_key

    @property
    def resolved_llm_base_url(self) -> str:
        return self.llm_base_url or self.anthropic_base_url

    @property
    def resolved_llm_model(self) -> str:
        return self.llm_model or self.anthropic_model or "claude-opus-4-7"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
