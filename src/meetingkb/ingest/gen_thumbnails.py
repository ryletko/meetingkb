"""Pre-generate seek-bar hover-preview thumbnails for every indexed meeting."""
from __future__ import annotations

import logging
from pathlib import Path

from meetingkb.config import Settings
from meetingkb.ingest import thumbnails
from meetingkb.search.storage import connect

logger = logging.getLogger(__name__)


def generate_all(settings: Settings) -> int:
    """Generate storyboard thumbnails for every meeting missing them.

    Returns the number of meetings for which thumbnails were generated.
    """
    conn = connect(settings.db_path)
    try:
        rows = conn.execute(
            "SELECT id, title, source_path FROM meetings ORDER BY meeting_date, title"
        ).fetchall()
    finally:
        conn.close()

    generated = 0
    for row in rows:
        meeting_id = row["id"]
        source = row["source_path"]
        title = row["title"] or meeting_id
        if not source:
            logger.info("skip %s: no source video", title)
            continue
        if thumbnails.has_thumbnails(settings.data_dir, meeting_id):
            logger.info("cached %s", title)
            continue
        try:
            out = thumbnails.generate(settings.data_dir, meeting_id, Path(source))
        except Exception:  # noqa: BLE001 - report and continue
            logger.exception("failed to generate thumbnails for %s", title)
            continue
        if out is None:
            logger.info("skipped %s: missing video / no frames", title)
            continue
        generated += 1
    return generated
