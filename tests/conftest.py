"""Shared test fixtures.

Keep the suite hermetic: the product encourages a local ``.env`` (KB_DATA_DIR,
KB_TERMS_FILE, KB_OPENSEARCH_ENABLED, ...) for local runs, and reads ``KB_*``
environment variables. Neither should leak into ``Settings()`` constructed in
tests — otherwise a developer's own ``.env`` would flip test assertions. Tests
set whatever environment they need explicitly via ``monkeypatch``.
"""
import os

import pytest

from meetingkb.config import Settings, get_settings


@pytest.fixture(autouse=True)
def _isolate_settings_from_local_env(monkeypatch):
    for key in list(os.environ):
        if key.startswith("KB_"):
            monkeypatch.delenv(key, raising=False)
    # Ignore any on-disk .env for the duration of the test.
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
