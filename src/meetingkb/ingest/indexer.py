"""Meeting indexer: Whisper JSON transcripts -> SQLite + OpenSearch.

Ported from the original ingestion script. Configuration
(paths, canonical terms, OpenSearch endpoints) is injected via a
``meetingkb.config.Settings`` instance instead of being read from
module-level constants.
"""
from __future__ import annotations

import json
import logging
import re
import sqlite3
from collections import Counter
from dataclasses import replace
from pathlib import Path
from typing import Any

from meetingkb.config import Settings
from meetingkb.ingest.transcripts import (
    load_whisper_json,
    parse_meeting_date,
    segments_from_whisper,
    slugify,
    timestamp_label,
)
from meetingkb.models import Meeting, Segment
from meetingkb.search.opensearch_backend import OpenSearchClient
from meetingkb.search.storage import connect, init_db

logger = logging.getLogger(__name__)


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
    segments: list[Segment], patterns: dict[str, list[re.Pattern[str]]]
) -> tuple[Counter[str], dict[str, float]]:
    counts: Counter[str] = Counter()
    first_seen: dict[str, float] = {}
    for segment in segments:
        for term in _detect_terms(segment.text, patterns):
            counts[term] += 1
            first_seen.setdefault(term, segment.start_sec)
    return counts, first_seen


def reset_sqlite(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM segment_fts")
    conn.execute("DELETE FROM terms")
    conn.execute("DELETE FROM segments")
    conn.execute("DELETE FROM meetings")
    conn.commit()


def _meeting_doc(meeting: Meeting, terms: list[str]) -> dict[str, Any]:
    """Serialize a `Meeting` to the OpenSearch/legacy dict shape (unchanged keys)."""
    return {
        "id": meeting.id,
        "title": meeting.title,
        "meeting_date": meeting.meeting_date,
        "source_path": meeting.source_path,
        "transcript_json_path": meeting.transcript_json_path,
        "transcript_txt_path": meeting.transcript_txt_path,
        "duration_sec": meeting.duration_sec,
        "duration_label": timestamp_label(meeting.duration_sec),
        "language": meeting.language,
        "model": meeting.model,
        "segment_count": meeting.segment_count,
        "term_count": meeting.term_count,
        "terms": terms,
        "term_text": " ".join(terms),
    }


def _segment_doc(segment: Segment, meeting: Meeting) -> dict[str, Any]:
    """Serialize a `Segment` (+ owning `Meeting`) to the OpenSearch/legacy dict shape."""
    return {
        "id": segment.id,
        "meeting_id": segment.meeting_id,
        "title": meeting.title,
        "meeting_date": meeting.meeting_date,
        "source_path": meeting.source_path,
        "transcript_json_path": meeting.transcript_json_path,
        "transcript_txt_path": meeting.transcript_txt_path,
        "segment_index": segment.segment_index,
        "start_sec": segment.start_sec,
        "end_sec": segment.end_sec,
        "start_label": timestamp_label(segment.start_sec),
        "end_label": timestamp_label(segment.end_sec),
        "duration_sec": max(0.0, segment.end_sec - segment.start_sec),
        "text": segment.text,
        "terms": segment.terms,
        "term_text": " ".join(segment.terms),
        "model": meeting.model,
    }


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
        raw_segments = data.get("segments", [])
        if not isinstance(raw_segments, list):
            continue

        stem = json_path.stem
        meeting_id = slugify(stem)
        title = stem
        txt_path = transcript_dir / f"{stem}.txt"
        source_path = find_source(root, stem, settings.media_extensions)
        meeting_date = parse_meeting_date(
            stem, source_path.stat().st_mtime if source_path else json_path.stat().st_mtime
        )

        all_segments = segments_from_whisper(meeting_id, data)
        duration_sec = max((s.end_sec for s in all_segments), default=0.0)
        term_counts, first_seen = _count_meeting_terms(all_segments, patterns)
        all_terms = sorted(term_counts)

        meeting = Meeting(
            id=meeting_id,
            title=title,
            meeting_date=meeting_date,
            source_path=str(source_path) if source_path else None,
            transcript_json_path=str(json_path),
            transcript_txt_path=str(txt_path) if txt_path.exists() else None,
            duration_sec=duration_sec,
            language=data.get("language"),
            model=model,
            segment_count=len(all_segments),
            term_count=sum(term_counts.values()),
        )

        conn.execute(
            """
            INSERT INTO meetings(
                id, title, meeting_date, source_path, transcript_json_path, transcript_txt_path,
                duration_sec, language, model, segment_count, term_count, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                meeting.id,
                meeting.title,
                meeting.meeting_date,
                meeting.source_path,
                meeting.transcript_json_path,
                meeting.transcript_txt_path,
                meeting.duration_sec,
                meeting.language,
                meeting.model,
                meeting.segment_count,
                meeting.term_count,
            ),
        )

        for term, count in term_counts.items():
            conn.execute(
                "INSERT INTO terms(meeting_id, term, count, first_start_sec) VALUES (?, ?, ?, ?)",
                (meeting_id, term, count, first_seen.get(term)),
            )

        meeting_docs.append(_meeting_doc(meeting, all_terms))

        for segment in all_segments:
            if not segment.text.strip():
                continue
            terms = detect_terms(segment.text, settings.terms)
            segment = replace(segment, terms=terms)
            terms_json = json.dumps(segment.terms, ensure_ascii=False)
            conn.execute(
                """
                INSERT INTO segments(id, meeting_id, segment_index, start_sec, end_sec, text, terms)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    segment.id,
                    segment.meeting_id,
                    segment.segment_index,
                    segment.start_sec,
                    segment.end_sec,
                    segment.text,
                    terms_json,
                ),
            )
            conn.execute(
                """
                INSERT INTO segment_fts(segment_id, meeting_id, title, text, terms)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    segment.id,
                    segment.meeting_id,
                    meeting.title,
                    segment.text,
                    " ".join(segment.terms),
                ),
            )
            segment_docs.append(_segment_doc(segment, meeting))

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
        logger.warning(
            "OpenSearch is not available at %s; skipped OpenSearch indexing",
            settings.opensearch_url,
        )
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
