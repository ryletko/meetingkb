from meetingkb.models import Meeting, SearchHit, Segment


def test_segment_roundtrip():
    seg = Segment(id="m1_00001", meeting_id="m1", segment_index=1,
                  start_sec=0.0, end_sec=5.0, text="hi", terms=["Alpha"])
    assert seg.terms == ["Alpha"]
    assert seg.id == "m1_00001"


def test_searchhit_fields():
    hit = SearchHit(id="m1_00001", meeting_id="m1", title="T", meeting_date="2026-01-01",
                    source_path="/x.webm", segment_index=1, start_sec=0.0, end_sec=5.0,
                    start_label="00:00:00", end_label="00:00:05", text="hi",
                    terms=["Alpha"], score=1.0)
    assert hit.score == 1.0


def test_meeting_defaults():
    m = Meeting(id="m1", title="T", meeting_date=None, source_path=None,
                transcript_json_path="/x.json", transcript_txt_path=None,
                duration_sec=None, language="en", model="whisper-medium",
                segment_count=0, term_count=0)
    assert m.segment_count == 0
