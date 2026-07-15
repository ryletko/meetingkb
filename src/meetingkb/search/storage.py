from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS meetings (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    meeting_date TEXT,
    source_path TEXT,
    transcript_json_path TEXT NOT NULL,
    transcript_txt_path TEXT,
    duration_sec REAL,
    language TEXT,
    model TEXT,
    segment_count INTEGER NOT NULL DEFAULT 0,
    term_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS segments (
    id TEXT PRIMARY KEY,
    meeting_id TEXT NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    segment_index INTEGER NOT NULL,
    start_sec REAL NOT NULL,
    end_sec REAL NOT NULL,
    text TEXT NOT NULL,
    terms TEXT NOT NULL DEFAULT '[]'
);

CREATE INDEX IF NOT EXISTS idx_segments_meeting_start
ON segments(meeting_id, start_sec);

CREATE TABLE IF NOT EXISTS terms (
    meeting_id TEXT NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    term TEXT NOT NULL,
    count INTEGER NOT NULL,
    first_start_sec REAL,
    PRIMARY KEY (meeting_id, term)
);

CREATE VIRTUAL TABLE IF NOT EXISTS segment_fts USING fts5(
    segment_id UNINDEXED,
    meeting_id UNINDEXED,
    title,
    text,
    terms,
    tokenize='unicode61'
);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()
