"""Dependency-injection wiring: `Settings` -> storage/search/RAG/transcriber."""
from __future__ import annotations

import sqlite3

from meetingkb.config import Settings, get_settings
from meetingkb.ingest.transcriber import FasterWhisperTranscriber
from meetingkb.rag.client import LLMConfig, OpenAICompatibleClient
from meetingkb.search import storage
from meetingkb.search.opensearch_backend import OpenSearchClient
from meetingkb.search.service import SearchService


class AppContext:
    """Lazily builds and caches the services a `Settings` instance wires together."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._sqlite: sqlite3.Connection | None = None
        self._search_backend: OpenSearchClient | None = None
        self._transcriber: FasterWhisperTranscriber | None = None
        self._search_service: SearchService | None = None

    def sqlite(self) -> sqlite3.Connection:
        if self._sqlite is None:
            self._sqlite = storage.connect(self.settings.db_path)
        return self._sqlite

    def search_backend(self) -> OpenSearchClient:
        if self._search_backend is None:
            self._search_backend = OpenSearchClient(self.settings.opensearch_url)
        return self._search_backend

    def opensearch_available(self) -> bool:
        return self.search_backend().available()

    def search_service(self) -> SearchService:
        if self._search_service is None:
            self._search_service = SearchService(
                self.sqlite(), self.search_backend(), self.settings
            )
        return self._search_service

    def llm_client(self, config: LLMConfig) -> OpenAICompatibleClient:
        return OpenAICompatibleClient(config)

    def transcriber(self) -> FasterWhisperTranscriber:
        if self._transcriber is None:
            self._transcriber = FasterWhisperTranscriber(self.settings)
        return self._transcriber


def build_context(settings: Settings | None = None) -> AppContext:
    return AppContext(settings or get_settings())
