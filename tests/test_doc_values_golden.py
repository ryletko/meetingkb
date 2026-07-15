"""Golden regression test for serialized meeting/segment document values.

`index_sqlite()` (via `_meeting_doc`/`_segment_doc` in
`meetingkb.ingest.indexer`) turns a Whisper transcript into the exact dict
shape written to SQLite and, when enabled, bulk-indexed into OpenSearch.
`test_indexer.py::test_index_sqlite_doc_shapes` only locks the *keys*; this
test locks every *value* -- duration/label formatting, term detection,
`meeting_date` parsing, id derivation, model tag -- against one fully fixed
transcript fixture, so silent drift in any of those computations is caught.

`transcript_json_path` is the one field that legitimately varies (it is
derived from pytest's `tmp_path`), so it is asserted separately against the
actual fixture path rather than hard-coded.
"""
from __future__ import annotations

import json

from meetingkb.config import Settings
from meetingkb.ingest.indexer import index_sqlite
from meetingkb.ingest.transcripts import slugify
from meetingkb.search.storage import connect, init_db

STEM = "Standup 01.03.2026 09-00-00"
MEETING_ID = slugify(STEM)

SEGMENTS = [
    {"start": 0.0, "end": 3.5, "text": "Alpha rollout is stable and ready"},
    {"start": 3.5, "end": 7.25, "text": "Beta pipeline still needs review"},
    {"start": 7.25, "end": 10.0, "text": "Alpha and Beta both shipped today"},
]

EXPECTED_MEETING_DOC = {
    "id": MEETING_ID,
    "title": STEM,
    "meeting_date": "2026-03-01T09:00:00",
    "source_path": None,
    # transcript_json_path is asserted separately (depends on tmp_path).
    "transcript_txt_path": None,
    "duration_sec": 10.0,
    "duration_label": "00:00:10",
    "language": "en",
    "model": "whisper-medium",
    "segment_count": 3,
    "term_count": 4,
    "terms": ["Alpha", "Beta"],
    "term_text": "Alpha Beta",
}

EXPECTED_SEGMENT_DOCS = [
    {
        "id": f"{MEETING_ID}_00000",
        "meeting_id": MEETING_ID,
        "title": STEM,
        "meeting_date": "2026-03-01T09:00:00",
        "source_path": None,
        "transcript_txt_path": None,
        "segment_index": 0,
        "start_sec": 0.0,
        "end_sec": 3.5,
        "start_label": "00:00:00",
        "end_label": "00:00:03",
        "duration_sec": 3.5,
        "text": "Alpha rollout is stable and ready",
        "terms": ["Alpha"],
        "term_text": "Alpha",
        "model": "whisper-medium",
    },
    {
        "id": f"{MEETING_ID}_00001",
        "meeting_id": MEETING_ID,
        "title": STEM,
        "meeting_date": "2026-03-01T09:00:00",
        "source_path": None,
        "transcript_txt_path": None,
        "segment_index": 1,
        "start_sec": 3.5,
        "end_sec": 7.25,
        "start_label": "00:00:03",
        "end_label": "00:00:07",
        "duration_sec": 3.75,
        "text": "Beta pipeline still needs review",
        "terms": ["Beta"],
        "term_text": "Beta",
        "model": "whisper-medium",
    },
    {
        "id": f"{MEETING_ID}_00002",
        "meeting_id": MEETING_ID,
        "title": STEM,
        "meeting_date": "2026-03-01T09:00:00",
        "source_path": None,
        "transcript_txt_path": None,
        "segment_index": 2,
        "start_sec": 7.25,
        "end_sec": 10.0,
        "start_label": "00:00:07",
        "end_label": "00:00:10",
        "duration_sec": 2.75,
        "text": "Alpha and Beta both shipped today",
        "terms": ["Alpha", "Beta"],
        "term_text": "Alpha Beta",
        "model": "whisper-medium",
    },
]


def _write_fixture(tmp_path):
    tdir = tmp_path / "transcripts"
    tdir.mkdir(parents=True)
    (tdir / f"{STEM}.json").write_text(
        json.dumps({"language": "en", "segments": SEGMENTS}), encoding="utf-8"
    )
    terms_file = tmp_path / "terms.txt"
    terms_file.write_text("Alpha\nBeta\n", encoding="utf-8")
    return tdir, terms_file


def test_meeting_and_segment_docs_match_golden_values(tmp_path):
    tdir, terms_file = _write_fixture(tmp_path)
    settings = Settings(data_dir=tmp_path, terms_file=terms_file)
    conn = connect(settings.db_path)
    init_db(conn)
    try:
        meeting_docs, segment_docs = index_sqlite(conn, settings)
    finally:
        conn.close()

    expected_json_path = str(tdir / f"{STEM}.json")

    assert len(meeting_docs) == 1
    meeting_doc = dict(meeting_docs[0])
    assert meeting_doc.pop("transcript_json_path") == expected_json_path
    assert meeting_doc == EXPECTED_MEETING_DOC

    assert len(segment_docs) == len(EXPECTED_SEGMENT_DOCS)
    for actual, expected in zip(segment_docs, EXPECTED_SEGMENT_DOCS, strict=True):
        actual = dict(actual)
        assert actual.pop("transcript_json_path") == expected_json_path
        assert actual == expected
