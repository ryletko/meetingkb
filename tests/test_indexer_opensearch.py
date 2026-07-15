import json

import pytest

from meetingkb.config import Settings
from meetingkb.ingest.indexer import build_index
from meetingkb.search.opensearch_backend import OpenSearchClient


def _write_transcript(dir_, stem, segments):
    dir_.mkdir(parents=True, exist_ok=True)
    (dir_ / f"{stem}.json").write_text(
        json.dumps({"language": "en", "segments": segments}), encoding="utf-8")


@pytest.mark.integration
def test_build_index_populates_opensearch(tmp_path):
    tdir = tmp_path / "transcripts"
    _write_transcript(tdir, "Standup 01.02.2026 09-00-00",
                      [{"start": 0.0, "end": 3.0, "text": "Alpha is ready"},
                       {"start": 3.0, "end": 6.0, "text": "Beta pipeline green"}])
    settings = Settings(
        data_dir=tmp_path,
        os_meetings_index="meetingkb_test_meetings",
        os_segments_index="meetingkb_test_segments",
    )
    result = build_index(settings, use_opensearch=True)
    assert result["meetings"] == 1
    assert result["segments"] == 2
    assert result["opensearch"] is True

    client = OpenSearchClient(settings.opensearch_url)
    meeting_hits = client.search(settings.os_meetings_index, {"query": {"match_all": {}}})
    assert meeting_hits["hits"]["total"]["value"] == 1

    segment_hits = client.search(
        settings.os_segments_index, {"query": {"match": {"text": "Alpha"}}}
    )
    assert segment_hits["hits"]["total"]["value"] == 1
