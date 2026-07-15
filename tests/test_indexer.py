import json

from meetingkb.config import Settings
from meetingkb.ingest.indexer import build_index, detect_terms, index_sqlite
from meetingkb.search.storage import connect, init_db


def test_detect_terms_uses_injected_list():
    assert detect_terms("The Alpha build failed", ["Alpha", "Beta"]) == ["Alpha"]


def _write_transcript(dir_, stem, segments):
    dir_.mkdir(parents=True, exist_ok=True)
    (dir_ / f"{stem}.json").write_text(
        json.dumps({"language": "en", "segments": segments}), encoding="utf-8")


def test_build_index_populates_sqlite(tmp_path):
    tdir = tmp_path / "transcripts"
    _write_transcript(tdir, "Standup 01.02.2026 09-00-00",
                      [{"start": 0.0, "end": 3.0, "text": "Alpha is ready"},
                       {"start": 3.0, "end": 6.0, "text": "Beta pipeline green"}])
    settings = Settings(data_dir=tmp_path)
    result = build_index(settings, use_opensearch=False)
    assert result["meetings"] == 1
    assert result["segments"] == 2
    conn = connect(settings.db_path)
    assert conn.execute("SELECT count(*) FROM segments").fetchone()[0] == 2
    hit = conn.execute(
        "SELECT segment_id FROM segment_fts WHERE segment_fts MATCH 'Alpha'").fetchone()
    assert hit is not None


def test_build_index_skips_empty_segment_preserves_index_gap(tmp_path):
    tdir = tmp_path / "transcripts"
    _write_transcript(
        tdir,
        "Standup 02.02.2026 09-00-00",
        [
            {"start": 0.0, "end": 3.0, "text": "Alpha ready"},
            {"start": 3.0, "end": 4.0, "text": "   "},
            {"start": 4.0, "end": 7.0, "text": "Gamma done"},
        ],
    )
    settings = Settings(data_dir=tmp_path)
    result = build_index(settings, use_opensearch=False)
    assert result["segments"] == 2
    conn = connect(settings.db_path)
    segment_indices = [
        r[0]
        for r in conn.execute(
            "SELECT segment_index FROM segments ORDER BY segment_index"
        )
    ]
    assert segment_indices == [0, 2]


def test_build_index_duration_sec_ignores_missing_end_default(tmp_path):
    tdir = tmp_path / "transcripts"
    _write_transcript(
        tdir,
        "Standup 04.02.2026 09-00-00",
        [
            {"start": 0.0, "end": 3.0, "text": "Alpha ready"},
            {"start": 5.0, "text": "Beta has no end key"},
        ],
    )
    settings = Settings(data_dir=tmp_path)
    build_index(settings, use_opensearch=False)
    conn = connect(settings.db_path)
    duration_sec = conn.execute("SELECT duration_sec FROM meetings").fetchone()[0]
    assert duration_sec == 3.0


def test_index_sqlite_doc_shapes(tmp_path):
    tdir = tmp_path / "transcripts"
    _write_transcript(tdir, "Standup 03.02.2026 09-00-00",
                      [{"start": 0.0, "end": 3.0, "text": "Alpha is ready"}])
    settings = Settings(data_dir=tmp_path)
    conn = connect(settings.db_path)
    init_db(conn)
    try:
        meeting_docs, segment_docs = index_sqlite(conn, settings)
    finally:
        conn.close()

    assert len(meeting_docs) == 1
    assert set(meeting_docs[0].keys()) == {
        "id", "title", "meeting_date", "source_path", "transcript_json_path",
        "transcript_txt_path", "duration_sec", "duration_label", "language",
        "model", "segment_count", "term_count", "terms", "term_text",
    }

    assert len(segment_docs) == 1
    assert set(segment_docs[0].keys()) == {
        "id", "meeting_id", "title", "meeting_date", "source_path",
        "transcript_json_path", "transcript_txt_path", "segment_index",
        "start_sec", "end_sec", "start_label", "end_label", "duration_sec",
        "text", "terms", "term_text", "model",
    }
