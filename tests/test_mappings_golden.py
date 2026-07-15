"""Golden regression test for the OpenSearch index mappings.

`meetings_mapping()` and `segments_mapping()` are pure functions (no
OpenSearch required) that define the on-disk shape of every indexed
document -- field types, keyword sub-fields, `ignore_above` truncation
limits, shard/replica settings. A change here is a silent breaking change
to search relevance/filtering/sorting for anyone with an existing index
(e.g. `terms` switching from `keyword` to `text` would break exact-term
filtering; dropping `ignore_above` could blow up indexing on long paths).

These dicts are hard-coded to the mapping as read on 2026-07-15 (see
`.superpowers/sdd/issue8-golden-report.md`). Any intentional mapping change
must update this test in the same commit.
"""
from __future__ import annotations

from meetingkb.ingest.indexer import meetings_mapping, segments_mapping

EXPECTED_MEETINGS_MAPPING = {
    "settings": {"index": {"number_of_shards": 1, "number_of_replicas": 0}},
    "mappings": {
        "properties": {
            "id": {"type": "keyword"},
            "title": {
                "type": "text",
                "fields": {"keyword": {"type": "keyword", "ignore_above": 512}},
            },
            "meeting_date": {"type": "date"},
            "source_path": {
                "type": "text",
                "fields": {"keyword": {"type": "keyword", "ignore_above": 512}},
            },
            "transcript_json_path": {"type": "keyword", "ignore_above": 2048},
            "transcript_txt_path": {"type": "keyword", "ignore_above": 2048},
            "duration_sec": {"type": "float"},
            "duration_label": {"type": "keyword"},
            "language": {"type": "keyword"},
            "model": {"type": "keyword"},
            "segment_count": {"type": "integer"},
            "term_count": {"type": "integer"},
            "terms": {"type": "keyword"},
            "term_text": {"type": "text"},
        }
    },
}

EXPECTED_SEGMENTS_MAPPING = {
    "settings": {"index": {"number_of_shards": 1, "number_of_replicas": 0}},
    "mappings": {
        "properties": {
            "id": {"type": "keyword"},
            "meeting_id": {"type": "keyword"},
            "title": {
                "type": "text",
                "fields": {"keyword": {"type": "keyword", "ignore_above": 512}},
            },
            "meeting_date": {"type": "date"},
            "source_path": {
                "type": "text",
                "fields": {"keyword": {"type": "keyword", "ignore_above": 512}},
            },
            "transcript_json_path": {"type": "keyword", "ignore_above": 2048},
            "transcript_txt_path": {"type": "keyword", "ignore_above": 2048},
            "segment_index": {"type": "integer"},
            "start_sec": {"type": "float"},
            "end_sec": {"type": "float"},
            "start_label": {"type": "keyword"},
            "end_label": {"type": "keyword"},
            "duration_sec": {"type": "float"},
            "text": {"type": "text"},
            "terms": {"type": "keyword"},
            "term_text": {"type": "text"},
            "model": {"type": "keyword"},
        }
    },
}


def test_meetings_mapping_matches_golden():
    assert meetings_mapping() == EXPECTED_MEETINGS_MAPPING


def test_segments_mapping_matches_golden():
    assert segments_mapping() == EXPECTED_SEGMENTS_MAPPING
