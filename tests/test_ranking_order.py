"""Golden regression test for search RESULT ORDER (not just membership).

`SearchService._search_sqlite` merges the SQLite FTS path (bm25-ranked exact
matches) first, then tops up with the fuzzy/transliteration path
(`fuzzy_match_query`-ranked) for whatever the FTS pass didn't already find.
A ranking regression (e.g. reordering the merge, or reversing the bm25
sort) would silently degrade relevance without breaking any "hits contain
X" style assertion -- this test asserts the exact ordered id sequence.

The fixture is built so the ordering is deterministic without depending on
exact bm25 floating-point values: "deploy" appears verbatim in segment 0
(an FTS exact-term hit) and only as the typo "deploi" in segment 1 (not a
token in the `unicode61` FTS index at all -- it can only surface via the
fuzzy/Levenshtein path). Segment 2 shares no tokens with the query and must
be excluded entirely. The exact-match hit must therefore strictly precede
the typo-only fuzzy hit.
"""
from __future__ import annotations

import json

from meetingkb.config import Settings
from meetingkb.context import build_context
from meetingkb.ingest.indexer import build_index

STEM = "Standup 02.03.2026 09-00-00"

SEGMENTS = [
    {"start": 0.0, "end": 3.0, "text": "Deploy pipeline is green today"},
    {"start": 3.0, "end": 6.0, "text": "The deploi confirmation was late"},
    {"start": 6.0, "end": 9.0, "text": "Standup notes about hiring plans"},
]


def _write_fixture(tmp_path):
    tdir = tmp_path / "transcripts"
    tdir.mkdir(parents=True)
    (tdir / f"{STEM}.json").write_text(
        json.dumps({"language": "en", "segments": SEGMENTS}), encoding="utf-8"
    )


def test_exact_match_ranks_before_typo_only_fuzzy_match(tmp_path):
    _write_fixture(tmp_path)
    settings = Settings(data_dir=tmp_path)
    build_index(settings, use_opensearch=False)

    ctx = build_context(settings)
    hits = ctx.search_service().search("deploy", None, None, 10, opensearch_available=False)

    assert [hit.text for hit in hits] == [
        "Deploy pipeline is green today",
        "The deploi confirmation was late",
    ]
    assert hits[0].match_source == ""  # bm25/FTS exact match, not a fallback path
    assert hits[1].match_source == "fuzzy/transliteration"
    assert hits[0].id.endswith("_00000")
    assert hits[1].id.endswith("_00001")
