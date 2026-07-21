"""Transcript parsing: Whisper JSON -> domain models.

Holds the filename/timestamp helpers used by the indexer (``slugify``,
``parse_meeting_date``, ``timestamp_label``, ``load_json``). Term detection is
intentionally not included here; it belongs to the indexer.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from meetingkb.models import Segment


def slugify(value: str) -> str:
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:16]
    return f"m_{digest}"


def parse_meeting_date(stem: str, fallback: float | None = None) -> str | None:
    patterns = [
        (r"(\d{2})\.(\d{2})\.(\d{4})\s+(\d{2})-(\d{2})-(\d{2})", "%d.%m.%Y %H-%M-%S"),
        (r"(\d{2})\.(\d{2})\.(\d{2})\s+(\d{2})-(\d{2})-(\d{2})", "%d.%m.%y %H-%M-%S"),
    ]
    for pattern, fmt in patterns:
        match = re.search(pattern, stem)
        if match:
            try:
                return datetime.strptime(match.group(0), fmt).isoformat(timespec="seconds")
            except ValueError:
                pass
    if fallback:
        return datetime.fromtimestamp(fallback).isoformat(timespec="seconds")
    return None


def timestamp_label(seconds: float) -> str:
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def load_whisper_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def segments_from_whisper(meeting_id: str, data: dict[str, Any]) -> list[Segment]:
    segments: list[Segment] = []
    for i, raw in enumerate(data.get("segments", [])):
        start_sec = float(raw.get("start", 0.0))
        end_sec = float(raw.get("end", start_sec))
        segments.append(
            Segment(
                id=f"{meeting_id}_{i:05d}",
                meeting_id=meeting_id,
                segment_index=i,
                start_sec=start_sec,
                end_sec=end_sec,
                text=str(raw.get("text", "")).strip(),
                terms=[],
            )
        )
    return segments
