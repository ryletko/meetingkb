"""Search orchestration: merges SQLite FTS/fuzzy and OpenSearch lookups behind one service.

Moved out of `meetingkb.web.app` (the Streamlit UI) so the UI only collects
filters and renders results. This module owns query building, backend
dispatch/fallback, merge/dedup/ranking, highlighting, and `SearchHit`
construction -- a straight port of the former app.py functions, wired to
injected dependencies (`conn`, `backend`, `settings`) instead of Streamlit
globals.
"""
from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import replace

import requests

from meetingkb.config import Settings
from meetingkb.models import SearchHit
from meetingkb.search.opensearch_backend import OpenSearchClient, OpenSearchError
from meetingkb.search.query import fuzzy_match_query, highlight_fuzzy, query_variants


def _seconds_label(seconds: float | int | None) -> str:
    if seconds is None:
        return "00:00:00"
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def build_filter(meeting_id: str | None, term: str | None) -> list[dict]:
    filters = []
    if meeting_id:
        filters.append({"term": {"meeting_id": meeting_id}})
    if term:
        filters.append({"term": {"terms": term}})
    return filters


def sqlite_fts_query(query: str) -> str:
    parts = []
    for token in re.findall(r"\S+", query.strip()):
        token = token.replace('"', '""')
        if token:
            parts.append(f'"{token}"')
    return " ".join(parts)


def opensearch_query_body(query: str, meeting_id: str | None, term: str | None, limit: int) -> dict:
    filters = build_filter(meeting_id, term)
    if query.strip():
        query_clause = {
            "multi_match": {
                "query": query,
                "fields": ["text^4", "title^2", "term_text"],
                "operator": "and",
                "fuzziness": "AUTO",
            }
        }
        sort = [
            {"_score": {"order": "desc"}},
            {"meeting_date": {"order": "asc"}},
            {"start_sec": {"order": "asc"}},
        ]
    else:
        query_clause = {"match_all": {}}
        sort = [{"meeting_date": {"order": "asc"}}, {"start_sec": {"order": "asc"}}]

    return {
        "size": limit,
        "query": {"bool": {"must": [query_clause], "filter": filters}},
        "highlight": {
            "pre_tags": ["<mark>"],
            "post_tags": ["</mark>"],
            "encoder": "html",
            "fields": {"text": {"number_of_fragments": 0}},
        },
        "sort": sort,
    }


def _hit_from_source(
    source: dict,
    hit_id: str,
    score: float | None,
    highlighted_text: str,
    match_source: str,
) -> SearchHit:
    """Build a `SearchHit` from an OpenSearch `_source` segment doc."""
    return SearchHit(
        id=hit_id,
        meeting_id=source.get("meeting_id") or "",
        title=source.get("title") or "",
        meeting_date=source.get("meeting_date") or "",
        source_path=source.get("source_path") or "",
        segment_index=source.get("segment_index"),
        start_sec=source.get("start_sec"),
        end_sec=source.get("end_sec"),
        start_label=source.get("start_label") or _seconds_label(source.get("start_sec")),
        end_label=source.get("end_label") or _seconds_label(source.get("end_sec")),
        text=source.get("text") or "",
        terms=source.get("terms") or [],
        score=float(score or 0.0),
        transcript_txt_path=source.get("transcript_txt_path") or "",
        transcript_json_path=source.get("transcript_json_path") or "",
        highlighted_text=highlighted_text or "",
        match_source=match_source or "",
    )


def _hit_from_row(
    row: sqlite3.Row,
    score: float,
    highlighted_text: str = "",
    match_source: str = "",
) -> SearchHit:
    """Build a `SearchHit` from a SQLite `segments`+`meetings` result row."""
    try:
        terms = json.loads(row["terms"] or "[]")
    except json.JSONDecodeError:
        terms = []
    return SearchHit(
        id=row["id"],
        meeting_id=row["meeting_id"],
        title=row["title"] or "",
        meeting_date=row["meeting_date"] or "",
        source_path=row["source_path"] or "",
        segment_index=row["segment_index"],
        start_sec=row["start_sec"],
        end_sec=row["end_sec"],
        start_label=_seconds_label(row["start_sec"]),
        end_label=_seconds_label(row["end_sec"]),
        text=row["text"] or "",
        terms=terms,
        score=float(score),
        transcript_txt_path=row["transcript_txt_path"] or "",
        transcript_json_path=row["transcript_json_path"] or "",
        highlighted_text=highlighted_text,
        match_source=match_source,
    )


class SearchService:
    """Orchestrates SQLite FTS/fuzzy and OpenSearch search, with fallback.

    A direct port of the former `meetingkb.web.app` search functions: the
    only change is that the SQLite connection, OpenSearch client, and
    settings are injected instead of read from Streamlit-cached module
    globals.
    """

    def __init__(
        self, conn: sqlite3.Connection, backend: OpenSearchClient, settings: Settings
    ) -> None:
        self._conn = conn
        self._backend = backend
        self._settings = settings

    def search(
        self,
        query: str,
        meeting_id: str | None,
        term: str | None,
        limit: int,
        opensearch_available: bool,
    ) -> list[SearchHit]:
        try:
            if opensearch_available:
                return self._search_opensearch(query, meeting_id, term, limit)
            return self._search_sqlite(query, meeting_id, term, limit)
        except (requests.RequestException, OpenSearchError):
            return self._search_sqlite(query, meeting_id, term, limit)

    def _search_opensearch(
        self, query: str, meeting_id: str | None, term: str | None, limit: int
    ) -> list[SearchHit]:
        merged: dict[str, SearchHit] = {}
        variants = query_variants(query) if query.strip() else [""]

        for variant in variants:
            body = opensearch_query_body(variant, meeting_id, term, limit)
            result = self._backend.search(self._settings.os_segments_index, body)
            for raw_hit in result.get("hits", {}).get("hits", []):
                source = dict(raw_hit.get("_source") or {})
                hit_id = source.get("id") or raw_hit.get("_id")
                if not hit_id or hit_id in merged:
                    continue
                highlights = raw_hit.get("highlight", {}).get("text") or []
                highlighted_text = highlights[0] if highlights else ""
                match_source = f"expanded query: {variant}" if variant != query.strip() else ""
                merged[hit_id] = _hit_from_source(
                    source, hit_id, raw_hit.get("_score"), highlighted_text, match_source
                )
            if len(merged) >= limit:
                break

        hits = list(merged.values())[:limit]
        if query.strip() and len(hits) < limit:
            seen = {hit.id for hit in hits}
            strict_fuzzy_hits = self._search_sqlite_fuzzy(query, meeting_id, term, limit)
            for hit in strict_fuzzy_hits:
                if hit.id in seen:
                    continue
                hits.append(hit)
                seen.add(hit.id)
                if len(hits) >= limit:
                    break
        return hits

    def _search_sqlite_fts(
        self, query: str, meeting_id: str | None, term: str | None, limit: int
    ) -> list[SearchHit]:
        conn = self._conn
        params: list[object] = []
        where = []
        if query.strip():
            where.append("segment_fts MATCH ?")
            params.append(sqlite_fts_query(query))
        if meeting_id:
            where.append("s.meeting_id = ?")
            params.append(meeting_id)
        if term:
            where.append("EXISTS (SELECT 1 FROM json_each(s.terms) WHERE value = ?)")
            params.append(term)

        where_sql = "WHERE " + " AND ".join(where) if where else ""
        if query.strip():
            # bm25() is only valid when the query uses a MATCH clause on the FTS table.
            score_sql = "bm25(segment_fts) AS score"
            order_sql = "ORDER BY bm25(segment_fts)"
        else:
            score_sql = "0.0 AS score"
            order_sql = "ORDER BY m.meeting_date, s.start_sec"
        sql = f"""
            SELECT
                s.id, s.meeting_id, s.segment_index, s.start_sec, s.end_sec, s.text, s.terms,
                m.title, m.meeting_date, m.source_path, m.transcript_txt_path,
                m.transcript_json_path, {score_sql}
            FROM segment_fts
            JOIN segments s ON s.id = segment_fts.segment_id
            JOIN meetings m ON m.id = s.meeting_id
            {where_sql}
            {order_sql}
            LIMIT ?
        """
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
        return [_hit_from_row(row, score=row["score"]) for row in rows]

    def _search_sqlite_fuzzy(
        self, query: str, meeting_id: str | None, term: str | None, limit: int
    ) -> list[SearchHit]:
        conn = self._conn
        params: list[object] = []
        where = []
        if meeting_id:
            where.append("s.meeting_id = ?")
            params.append(meeting_id)
        if term:
            where.append("EXISTS (SELECT 1 FROM json_each(s.terms) WHERE value = ?)")
            params.append(term)
        where_sql = "WHERE " + " AND ".join(where) if where else ""
        rows = conn.execute(
            f"""
            SELECT
                s.id, s.meeting_id, s.segment_index, s.start_sec, s.end_sec, s.text, s.terms,
                m.title, m.meeting_date, m.source_path, m.transcript_txt_path,
                m.transcript_json_path
            FROM segments s
            JOIN meetings m ON m.id = s.meeting_id
            {where_sql}
            """,
            params,
        ).fetchall()

        scored = []
        for row in rows:
            matched, score, matched_tokens = fuzzy_match_query(query, row["text"])
            if not matched:
                continue
            hit = _hit_from_row(
                row,
                score=float(score),
                highlighted_text=highlight_fuzzy(row["text"], matched_tokens),
                match_source="fuzzy/transliteration",
            )
            scored.append((score, hit.meeting_date or "", hit.start_sec, hit))

        scored.sort(key=lambda item: (-item[0], item[1], item[2]))
        return [hit for _, _, _, hit in scored[:limit]]

    def _search_sqlite(
        self, query: str, meeting_id: str | None, term: str | None, limit: int
    ) -> list[SearchHit]:
        merged: dict[str, SearchHit] = {}
        variants = query_variants(query) if query.strip() else [""]
        for variant in variants:
            for hit in self._search_sqlite_fts(variant, meeting_id, term, limit):
                hit_id = hit.id
                if hit_id and hit_id not in merged:
                    if variant != query.strip():
                        hit = replace(hit, match_source=f"expanded query: {variant}")
                    merged[hit_id] = hit
            if len(merged) >= limit:
                break

        if query.strip() and len(merged) < limit:
            for hit in self._search_sqlite_fuzzy(query, meeting_id, term, limit):
                hit_id = hit.id
                if hit_id and hit_id not in merged:
                    merged[hit_id] = hit
                if len(merged) >= limit:
                    break
        return list(merged.values())[:limit]
