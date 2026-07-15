"""Out-of-the-box smoke test: index the bundled sample data into a temp SQLite
DB (no Docker/OpenSearch involved) and confirm the app boots and can search it.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from streamlit.testing.v1 import AppTest

from meetingkb.config import get_settings
from meetingkb.ingest.indexer import build_index

REPO_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_DATA_SRC = REPO_ROOT / "sample_data"
APP_PATH = REPO_ROOT / "src" / "meetingkb" / "web" / "app.py"

# A guaranteed-closed local port: keeps opensearch_available() False so the
# app takes its SQLite fallback path and never touches a real OpenSearch.
CLOSED_OPENSEARCH_URL = "http://127.0.0.1:59999"


def _expected_counts(transcripts_dir: Path) -> tuple[int, int]:
    """Compute expected (meetings, segments) straight from the fixture JSON."""
    meetings = 0
    segments = 0
    for json_path in sorted(transcripts_dir.glob("*.json")):
        data = json.loads(json_path.read_text(encoding="utf-8"))
        meetings += 1
        segments += sum(
            1 for seg in data.get("segments", []) if str(seg.get("text", "")).strip()
        )
    return meetings, segments


def _index_sample_data_into_tmp(tmp_path: Path, monkeypatch) -> tuple[Path, dict]:
    """Copy sample_data/ under tmp_path, point settings at it, and build the index."""
    data_dir = tmp_path / "sample_data"
    shutil.copytree(SAMPLE_DATA_SRC, data_dir)

    monkeypatch.setenv("KB_DATA_DIR", str(data_dir))
    monkeypatch.setenv("KB_OPENSEARCH_URL", CLOSED_OPENSEARCH_URL)
    monkeypatch.setenv("KB_TERMS_FILE", str(data_dir / "terms.txt"))
    get_settings.cache_clear()

    settings = get_settings()
    result = build_index(settings, use_opensearch=False)
    return data_dir, result


def test_build_index_matches_fixture_counts(tmp_path, monkeypatch):
    data_dir, result = _index_sample_data_into_tmp(tmp_path, monkeypatch)
    expected_meetings, expected_segments = _expected_counts(data_dir / "transcripts")

    assert expected_meetings == 2
    assert result["meetings"] == expected_meetings
    assert result["segments"] == expected_segments
    assert result["opensearch"] is False


def test_app_runs_without_exception(tmp_path, monkeypatch):
    _index_sample_data_into_tmp(tmp_path, monkeypatch)

    at = AppTest.from_file(str(APP_PATH), default_timeout=30).run()

    assert not at.exception
    rendered_text = [
        element.value if hasattr(element, "value") else ""
        for element in [*at.markdown, *at.title]
    ]
    assert any("Meeting Knowledge Base" in text for text in rendered_text)


def test_sample_data_is_searchable(tmp_path, monkeypatch):
    _index_sample_data_into_tmp(tmp_path, monkeypatch)

    # get_settings() is lru_cache'd; the env is already set for this test, and
    # the cache above was populated from the same env, so a fresh import of
    # the app module (deferred here so `st.set_page_config` only runs after
    # KB_DATA_DIR/KB_OPENSEARCH_URL point at our tmp fixtures) reads it back
    # consistently. Import lazily rather than at module scope for that reason.
    from meetingkb.web import app as kb_app

    hits = kb_app.search_sqlite("Alpha", None, None, 10)
    assert len(hits) >= 1
    assert all("alpha" in hit.text.lower() for hit in hits)
