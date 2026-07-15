"""Covers SearchService's OpenSearch-hit path (`_search_opensearch` / `_hit_from_source`)
and its request-time fallback to SQLite -- both previously untested. Uses an injected
fake backend so this stays a fast, network-free unit test (no real OpenSearch).
"""
import json

import requests

from meetingkb.config import Settings
from meetingkb.ingest.indexer import build_index
from meetingkb.search.service import SearchService
from meetingkb.search.storage import connect, init_db


class _CannedBackend:
    """Fake OpenSearchClient: `.search()` returns a fixed OpenSearch-shaped response."""

    def __init__(self, response: dict):
        self._response = response
        self.calls = 0

    def search(self, index: str, body: dict) -> dict:
        self.calls += 1
        return self._response


class _RaisingBackend:
    """Fake OpenSearchClient: `.search()` always raises, simulating an unreachable cluster."""

    def search(self, index: str, body: dict) -> dict:
        raise requests.RequestException("connection refused")


def _canned_response() -> dict:
    return {
        "hits": {
            "hits": [
                {
                    "_id": "opensearch-id-1",
                    "_score": 4.2,
                    "_source": {
                        "id": "seg-1",
                        "meeting_id": "m1",
                        "title": "Standup",
                        "meeting_date": "2026-02-01",
                        "source_path": "m1.mp4",
                        "segment_index": 0,
                        "start_sec": 0.0,
                        "end_sec": 3.0,
                        "start_label": "00:00:00",
                        "end_label": "00:00:03",
                        "text": "Alpha is ready",
                        "terms": ["Alpha"],
                        "transcript_txt_path": "m1.txt",
                        "transcript_json_path": "m1.json",
                    },
                    "highlight": {"text": ["<mark>Alpha</mark> is ready"]},
                },
                {
                    "_id": "opensearch-id-2",
                    "_score": 2.1,
                    "_source": {
                        "id": "seg-2",
                        "meeting_id": "m1",
                        "title": "Standup",
                        "meeting_date": "2026-02-01",
                        "source_path": "m1.mp4",
                        "segment_index": 1,
                        "start_sec": 3.0,
                        "end_sec": 6.0,
                        "start_label": "00:00:03",
                        "end_label": "00:00:06",
                        "text": "Beta pipeline green",
                        "terms": [],
                        "transcript_txt_path": "m1.txt",
                        "transcript_json_path": "m1.json",
                    },
                },
                # Duplicate of seg-1's id: must be deduped, not counted twice.
                {
                    "_id": "opensearch-id-1-dup",
                    "_score": 1.0,
                    "_source": {"id": "seg-1", "text": "Alpha is ready (dup)"},
                },
            ]
        }
    }


def test_search_opensearch_maps_source_fields_and_dedups(tmp_path):
    conn = connect(tmp_path / "knowledge.sqlite")
    init_db(conn)
    settings = Settings(data_dir=tmp_path)
    backend = _CannedBackend(_canned_response())
    service = SearchService(conn, backend, settings)

    hits = service.search("Alpha", None, None, 2, opensearch_available=True)

    # Dedup: 3 raw hits share 2 distinct ids -> 2 SearchHits, order preserved.
    assert [hit.id for hit in hits] == ["seg-1", "seg-2"]

    first = hits[0]
    assert first.meeting_id == "m1"
    assert first.title == "Standup"
    assert first.meeting_date == "2026-02-01"
    assert first.source_path == "m1.mp4"
    assert first.segment_index == 0
    assert first.start_sec == 0.0
    assert first.end_sec == 3.0
    assert first.start_label == "00:00:00"
    assert first.end_label == "00:00:03"
    assert first.text == "Alpha is ready"
    assert first.terms == ["Alpha"]
    assert first.score == 4.2
    assert first.transcript_txt_path == "m1.txt"
    assert first.transcript_json_path == "m1.json"
    assert first.highlighted_text == "<mark>Alpha</mark> is ready"

    second = hits[1]
    assert second.id == "seg-2"
    assert second.text == "Beta pipeline green"
    assert second.highlighted_text == ""  # no `highlight.text` on this raw hit

    # A single backend call was enough: merged already hit the limit after the
    # first (only) query variant, so no further variants were dispatched.
    assert backend.calls == 1


def _write_transcript(dir_, stem, segments):
    dir_.mkdir(parents=True, exist_ok=True)
    (dir_ / f"{stem}.json").write_text(
        json.dumps({"language": "en", "segments": segments}), encoding="utf-8"
    )


def test_search_falls_back_to_sqlite_when_opensearch_unreachable(tmp_path):
    tdir = tmp_path / "transcripts"
    _write_transcript(
        tdir,
        "Standup 01.02.2026 09-00-00",
        [{"start": 0.0, "end": 3.0, "text": "Alpha is ready"}],
    )
    settings = Settings(data_dir=tmp_path)
    build_index(settings, use_opensearch=False)

    conn = connect(settings.db_path)
    service = SearchService(conn, _RaisingBackend(), settings)

    hits = service.search("Alpha", None, None, 10, opensearch_available=True)

    # Falls back to the SQLite path despite opensearch_available=True, because
    # the backend raised requests.RequestException.
    assert hits
    assert any("Alpha" in hit.text for hit in hits)
