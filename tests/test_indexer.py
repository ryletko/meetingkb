import json

from meetingkb.config import Settings
from meetingkb.ingest.indexer import build_index, detect_terms
from meetingkb.search.storage import connect


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
