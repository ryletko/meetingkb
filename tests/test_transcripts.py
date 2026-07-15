from pathlib import Path

from meetingkb.ingest.transcripts import (
    load_whisper_json,
    parse_meeting_date,
    segments_from_whisper,
    slugify,
    timestamp_label,
)

FIX = Path(__file__).parent / "fixtures" / "sample.json"


def test_slugify_is_stable_and_prefixed():
    a = slugify("Meeting 03.07.2026")
    assert a.startswith("m_") and a == slugify("Meeting 03.07.2026")


def test_timestamp_label():
    assert timestamp_label(3661) == "01:01:01"


def test_parse_meeting_date_from_stem():
    assert parse_meeting_date("Запись встречи 03.07.2026 11-11-20").startswith("2026-07-03")


def test_segments_from_whisper():
    data = load_whisper_json(FIX)
    segs = segments_from_whisper("m1", data)
    assert len(segs) == 2
    assert segs[0].id == "m1_00000"
    assert segs[1].start_sec == 4.0
    assert "Beta" in segs[1].text
