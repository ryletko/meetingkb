"""Meeting indexer: Whisper JSON transcripts -> SQLite + OpenSearch.

Ported from the original ingestion script. Configuration
(paths, canonical terms, OpenSearch endpoints) is injected via a
``meetingkb.config.Settings`` instance instead of being read from
module-level constants.
"""
from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any

from meetingkb.config import Settings
from meetingkb.ingest.transcripts import (
    load_whisper_json,
    parse_meeting_date,
    slugify,
    timestamp_label,
)
from meetingkb.search.opensearch_backend import OpenSearchClient
from meetingkb.search.storage import connect, init_db


def find_source(root: Path, stem: str, media_extensions: frozenset[str]) -> Path | None:
    for path in root.iterdir():
        if path.is_file() and path.suffix.lower() in media_extensions and path.stem == stem:
            return path
    return None


def _term_patterns(terms: list[str]) -> dict[str, list[re.Pattern[str]]]:
    result: dict[str, list[re.Pattern[str]]] = {}
    for canonical in terms:
        variants = {canonical, canonical.lower()}
        result[canonical] = [re.compile(re.escape(v), re.IGNORECASE) for v in variants if v]
    return result


def _detect_terms(text: str, patterns: dict[str, list[re.Pattern[str]]]) -> list[str]:
    found = []
    for term, term_patterns in patterns.items():
        if any(pattern.search(text) for pattern in term_patterns):
            found.append(term)
    return found


def detect_terms(text: str, terms: list[str]) -> list[str]:
    """Return the subset of `terms` present in `text` (case-insensitive substring match)."""
    return _detect_terms(text, _term_patterns(terms))


def _count_meeting_terms(
    segments: list[dict[str, Any]], patterns: dict[str, list[re.Pattern[str]]]
) -> tuple[Counter[str], dict[str, float]]:
    counts: Counter[str] = Counter()
    first_seen: dict[str, float] = {}
    for segment in segments:
        text = segment.get("text", "")
        for term in _detect_terms(text, patterns):
            counts[term] += 1
            first_seen.setdefault(term, float(segment.get("start", 0.0)))
    return counts, first_seen


def reset_sqlite(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM segment_fts")
    conn.execute("DELETE FROM terms")
    conn.execute("DELETE FROM segments")
    conn.execute("DELETE FROM meetings")
    conn.commit()


def index_sqlite(
    conn: sqlite3.Connection, settings: Settings
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    root = settings.data_dir
    transcript_dir = settings.transcript_dir
    assert transcript_dir is not None
    patterns = _term_patterns(settings.terms)
    model = f"whisper-{settings.whisper_model}"

    meeting_docs: list[dict[str, Any]] = []
    segment_docs: list[dict[str, Any]] = []
    json_paths = sorted(transcript_dir.glob("*.json"), key=lambda p: p.name.lower())

    for json_path in json_paths:
        data = load_whisper_json(json_path)
        segments = data.get("segments", [])
        if not isinstance(segments, list):
            continue

        stem = json_path.stem
        meeting_id = slugify(stem)
        title = stem
        txt_path = transcript_dir / f"{stem}.txt"
        source_path = find_source(root, stem, settings.media_extensions)
        meeting_date = parse_meeting_date(
            stem, source_path.stat().st_mtime if source_path else json_path.stat().st_mtime
        )
        duration_sec = max((float(s.get("end", 0.0)) for s in segments), default=0.0)
        term_counts, first_seen = _count_meeting_terms(segments, patterns)
        all_terms = sorted(term_counts)

        conn.execute(
            """
            INSERT INTO meetings(
                id, title, meeting_date, source_path, transcript_json_path, transcript_txt_path,
                duration_sec, language, model, segment_count, term_count, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                meeting_id,
                title,
                meeting_date,
                str(source_path) if source_path else None,
                str(json_path),
                str(txt_path) if txt_path.exists() else None,
                duration_sec,
                data.get("language"),
                model,
                len(segments),
                sum(term_counts.values()),
            ),
        )

        for term, count in term_counts.items():
            conn.execute(
                "INSERT INTO terms(meeting_id, term, count, first_start_sec) VALUES (?, ?, ?, ?)",
                (meeting_id, term, count, first_seen.get(term)),
            )

        meeting_docs.append(
            {
                "id": meeting_id,
                "title": title,
                "meeting_date": meeting_date,
                "source_path": str(source_path) if source_path else None,
                "transcript_json_path": str(json_path),
                "transcript_txt_path": str(txt_path) if txt_path.exists() else None,
                "duration_sec": duration_sec,
                "duration_label": timestamp_label(duration_sec),
                "language": data.get("language"),
                "model": model,
                "segment_count": len(segments),
                "term_count": sum(term_counts.values()),
                "terms": all_terms,
                "term_text": " ".join(all_terms),
            }
        )

        for idx, segment in enumerate(segments):
            text = str(segment.get("text", "")).strip()
            if not text:
                continue
            start_sec = float(segment.get("start", 0.0))
            end_sec = float(segment.get("end", start_sec))
            segment_id = f"{meeting_id}_{idx:05d}"
            terms = _detect_terms(text, patterns)
            terms_json = json.dumps(terms, ensure_ascii=False)
            conn.execute(
                """
                INSERT INTO segments(id, meeting_id, segment_index, start_sec, end_sec, text, terms)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (segment_id, meeting_id, idx, start_sec, end_sec, text, terms_json),
            )
            conn.execute(
                """
                INSERT INTO segment_fts(segment_id, meeting_id, title, text, terms)
                VALUES (?, ?, ?, ?, ?)
                """,
                (segment_id, meeting_id, title, text, " ".join(terms)),
            )
            segment_docs.append(
                {
                    "id": segment_id,
                    "meeting_id": meeting_id,
                    "title": title,
                    "meeting_date": meeting_date,
                    "source_path": str(source_path) if source_path else None,
                    "transcript_json_path": str(json_path),
                    "transcript_txt_path": str(txt_path) if txt_path.exists() else None,
                    "segment_index": idx,
                    "start_sec": start_sec,
                    "end_sec": end_sec,
                    "start_label": timestamp_label(start_sec),
                    "end_label": timestamp_label(end_sec),
                    "duration_sec": max(0.0, end_sec - start_sec),
                    "text": text,
                    "terms": terms,
                    "term_text": " ".join(terms),
                    "model": model,
                }
            )

    conn.commit()
    return meeting_docs, segment_docs


def keyword_text_mapping() -> dict[str, Any]:
    return {"type": "text", "fields": {"keyword": {"type": "keyword", "ignore_above": 512}}}


def meetings_mapping() -> dict[str, Any]:
    return {
        "settings": {"index": {"number_of_shards": 1, "number_of_replicas": 0}},
        "mappings": {
            "properties": {
                "id": {"type": "keyword"},
                "title": keyword_text_mapping(),
                "meeting_date": {"type": "date"},
                "source_path": keyword_text_mapping(),
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


def segments_mapping() -> dict[str, Any]:
    return {
        "settings": {"index": {"number_of_shards": 1, "number_of_replicas": 0}},
        "mappings": {
            "properties": {
                "id": {"type": "keyword"},
                "meeting_id": {"type": "keyword"},
                "title": keyword_text_mapping(),
                "meeting_date": {"type": "date"},
                "source_path": keyword_text_mapping(),
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


def index_opensearch(
    settings: Settings, meeting_docs: list[dict[str, Any]], segment_docs: list[dict[str, Any]]
) -> bool:
    client = OpenSearchClient(settings.opensearch_url)
    if not client.available():
        return False

    client.update_cluster_settings(
        {
            "persistent": {
                "cluster.routing.allocation.disk.threshold_enabled": False,
                "cluster.blocks.create_index": None,
            }
        }
    )
    client.delete_index(settings.os_meetings_index)
    client.delete_index(settings.os_segments_index)
    client.create_index(settings.os_meetings_index, meetings_mapping())
    client.create_index(settings.os_segments_index, segments_mapping())
    client.bulk_index(settings.os_meetings_index, meeting_docs)
    client.bulk_index(settings.os_segments_index, segment_docs)
    return True


def build_index(settings: Settings, *, use_opensearch: bool = True) -> dict[str, Any]:
    """Build the SQLite (and, optionally, OpenSearch) meeting indexes.

    Returns ``{"meetings": int, "segments": int, "opensearch": bool}``.
    """
    conn = connect(settings.db_path)
    try:
        init_db(conn)
        reset_sqlite(conn)
        meeting_docs, segment_docs = index_sqlite(conn, settings)
    finally:
        conn.close()

    opensearch_indexed = False
    if use_opensearch:
        opensearch_indexed = index_opensearch(settings, meeting_docs, segment_docs)

    return {
        "meetings": len(meeting_docs),
        "segments": len(segment_docs),
        "opensearch": opensearch_indexed,
    }
