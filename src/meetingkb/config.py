"""Typed application settings, loaded from environment variables and `.env`."""
from __future__ import annotations

from functools import cached_property, lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

MEDIA_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".webm",
        ".mp4",
        ".mkv",
        ".mov",
        ".avi",
        ".m4a",
        ".mp3",
        ".wav",
        ".aac",
        ".ogg",
        ".opus",
    }
)

RAG_SYSTEM_PROMPT = (
    "You answer questions about meeting transcripts. Use only the transcript "
    "context supplied by the user. Answer in the same language as the "
    "question. If the context is insufficient, say the answer was not found "
    "in the transcripts. Cite sources inline as [S1], [S2]. Do not invent "
    "facts."
)


class Settings(BaseSettings):
    """Process-wide configuration, overridable via `KB_*` env vars or `.env`."""

    model_config = SettingsConfigDict(env_prefix="KB_", env_file=".env", extra="ignore")

    data_dir: Path = Path("./data")
    transcript_dir: Path | None = None
    db_path: Path | None = None

    opensearch_url: str = "http://127.0.0.1:9200"
    opensearch_enabled: bool = True
    os_meetings_index: str = "meetingkb_meetings"
    os_segments_index: str = "meetingkb_segments"

    language: str = "en"
    initial_prompt: str = ""
    terms_file: Path | None = None

    whisper_model: str = "medium"
    whisper_device: str = "auto"
    whisper_compute_type: str = "auto"

    llm_base_url: str = "http://127.0.0.1:11434/v1"
    llm_model: str = ""
    llm_api_key: str = ""
    rag_system_prompt: str = RAG_SYSTEM_PROMPT

    ui_port: int = 8502
    media_extensions: frozenset[str] = MEDIA_EXTENSIONS

    @model_validator(mode="after")
    def _derive_paths(self) -> Settings:
        # transcript_dir/db_path default to living under data_dir, but each is
        # intentionally independently overridable via KB_TRANSCRIPT_DIR /
        # KB_DB_PATH -- e.g. to put the database on a different disk.
        if self.transcript_dir is None:
            self.transcript_dir = self.data_dir / "transcripts"
        if self.db_path is None:
            self.db_path = self.data_dir / "knowledge.sqlite"
        return self

    @cached_property
    def terms(self) -> list[str]:
        """Terms loaded from `terms_file`, one per non-empty stripped line."""
        if self.terms_file is None:
            return []
        lines = self.terms_file.read_text(encoding="utf-8").splitlines()
        return [line.strip() for line in lines if line.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
