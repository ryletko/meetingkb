"""Regression test for the SQLite term filter.

`search_sqlite_fts`/`search_sqlite_fuzzy` must match a `term` filter exactly
against the segment's JSON `terms` array (via `json_each`) -- not with a raw
`LIKE '%"..."%'` pattern, where an unescaped `_`/`%` in the term acts as a
SQL wildcard. With the old LIKE-based filter, querying for term "A_B" would
also match a segment tagged only "A1B" (`_` matches any single character).
"""
import json

from meetingkb.config import get_settings
from meetingkb.ingest.indexer import build_index


def test_term_filter_is_exact_not_like_wildcard(tmp_path, monkeypatch):
    transcripts_dir = tmp_path / "transcripts"
    transcripts_dir.mkdir(parents=True)
    (transcripts_dir / "Standup 01.02.2026 09-00-00.json").write_text(
        json.dumps(
            {
                "language": "en",
                "segments": [
                    {"start": 0.0, "end": 3.0, "text": "Team discussed A_B rollout plan"},
                    {"start": 3.0, "end": 6.0, "text": "Team discussed A1B rollout plan"},
                ],
            }
        ),
        encoding="utf-8",
    )
    terms_file = tmp_path / "terms.txt"
    terms_file.write_text("A_B\nA1B\n", encoding="utf-8")

    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("KB_TERMS_FILE", str(terms_file))
    monkeypatch.setenv("KB_OPENSEARCH_URL", "http://127.0.0.1:59999")
    get_settings.cache_clear()

    settings = get_settings()
    build_index(settings, use_opensearch=False)

    # Import lazily, after env/cache are set -- see smoke_test.py's
    # `_index_sample_data_into_tmp` comment for why (module-level globals are
    # captured at import time). `db_conn`/`_ctx` are `st.cache_resource` with
    # no ttl, so also force them to rebuild: otherwise, if some earlier test
    # in this session already imported the app module and populated those
    # caches from its own tmp dir, `search_sqlite_fts` here would silently
    # query stale data instead of the terms.txt/transcript fixture above.
    from meetingkb.web import app as kb_app

    kb_app.db_conn.clear()
    kb_app._ctx.clear()

    hits = kb_app.search_sqlite_fts("", None, "A_B", 10)

    assert hits, "expected at least one hit for term 'A_B'"
    for hit in hits:
        assert "A_B" in hit.terms
        assert "A1B" not in hit.terms
