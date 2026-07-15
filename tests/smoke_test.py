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

    # Build the AppContext/SearchService directly against the tmp settings
    # populated above, rather than going through the Streamlit app module.
    from meetingkb.config import get_settings
    from meetingkb.context import build_context

    ctx = build_context(get_settings())
    hits = ctx.search_service().search("Alpha", None, None, 10, opensearch_available=False)
    assert len(hits) >= 1
    assert all("alpha" in hit.text.lower() for hit in hits)


def test_search_renders_result_cards(tmp_path, monkeypatch):
    """Regression guard for the SearchHit render-path conversion (B4 follow-up).

    The other smoke tests only boot the empty start screen or call
    `SearchService.search` directly — neither one actually renders a result card, so
    `result_block` / `context_block` / `render_files` / `_card_head_html` are
    unguarded against a stray dict-style `hit["x"]` access on a `SearchHit`.
    Driving a real "Alpha" query here forces those render paths to execute.
    """
    _index_sample_data_into_tmp(tmp_path, monkeypatch)

    at = AppTest.from_file(str(APP_PATH), default_timeout=30).run()
    assert not at.exception  # start screen boots clean (no query yet)

    # The search box is keyed into session_state under "q" (see `main()`'s
    # `st.text_input("Search", key="q", ...)`); setting it directly and
    # re-running is equivalent to a user typing into the box.
    at.session_state["q"] = "Alpha"
    at.run()

    assert not at.exception

    rendered_text = "\n".join(
        element.value for element in [*at.markdown, *at.title] if hasattr(element, "value")
    )
    assert "Alpha" in rendered_text
    # `kb-snippet` / `kb-card-head` only appear inside `result_block`'s markup,
    # so their presence proves a card actually rendered (not just "no crash").
    assert "kb-snippet" in rendered_text
    assert "kb-card-head" in rendered_text


def test_theater_focus_renders_without_exception(tmp_path, monkeypatch):
    """Cover `render_theater`'s SearchHit attribute access via the `focus` key.

    `main()` only calls `render_theater` when `st.session_state["focus"]`
    matches a hit id from the current search results, so a query must be set
    first (see `main()`: `focus` is only consulted after `has_query` is true
    and `hits` has been computed).
    """
    _index_sample_data_into_tmp(tmp_path, monkeypatch)

    from meetingkb.config import get_settings
    from meetingkb.context import build_context

    ctx = build_context(get_settings())
    hits = ctx.search_service().search("Alpha", None, None, 10, opensearch_available=False)
    assert hits, "expected at least one 'Alpha' hit to focus"

    at = AppTest.from_file(str(APP_PATH), default_timeout=30).run()
    at.session_state["q"] = "Alpha"
    at.session_state["focus"] = str(hits[0].id)
    at.run()

    assert not at.exception
    assert any("Back to results" in (button.label or "") for button in at.button)
