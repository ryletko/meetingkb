import dataclasses

import pytest

from meetingkb.models import Meeting, RagAnswer, RagDocument, SearchHit, Segment


def test_segment_roundtrip():
    seg = Segment(id="m1_00001", meeting_id="m1", segment_index=1,
                  start_sec=0.0, end_sec=5.0, text="hi", terms=["Alpha"])
    assert seg.terms == ["Alpha"]
    assert seg.id == "m1_00001"


def test_searchhit_fields():
    hit = SearchHit(id="m1_00001", meeting_id="m1", title="T", meeting_date="2026-01-01",
                    source_path="x.webm", segment_index=1, start_sec=0.0, end_sec=5.0,
                    start_label="00:00:00", end_label="00:00:05", text="hi",
                    terms=["Alpha"], score=1.0,
                    transcript_txt_path="x.txt", transcript_json_path="x.json",
                    highlighted_text="<mark>hi</mark>", match_source="fuzzy/transliteration")
    assert hit.score == 1.0
    assert hit.transcript_txt_path == "x.txt"
    assert hit.transcript_json_path == "x.json"
    assert hit.highlighted_text == "<mark>hi</mark>"
    assert hit.match_source == "fuzzy/transliteration"


def test_searchhit_optional_fields_default_empty():
    hit = SearchHit(id="m1_00001", meeting_id="m1", title="T", meeting_date="2026-01-01",
                    source_path="x.webm", segment_index=1, start_sec=0.0, end_sec=5.0,
                    start_label="00:00:00", end_label="00:00:05", text="hi",
                    terms=["Alpha"], score=1.0,
                    transcript_txt_path="x.txt", transcript_json_path="x.json")
    assert hit.highlighted_text == ""
    assert hit.match_source == ""


def test_meeting_defaults():
    m = Meeting(id="m1", title="T", meeting_date=None, source_path=None,
                transcript_json_path="x.json", transcript_txt_path=None,
                duration_sec=None, language="en", model="whisper-medium",
                segment_count=0, term_count=0)
    assert m.segment_count == 0


def test_model_immutability():
    """Test that models are frozen and cannot be mutated."""
    seg = Segment(id="m1_00001", meeting_id="m1", segment_index=1,
                  start_sec=0.0, end_sec=5.0, text="hi")
    with pytest.raises(dataclasses.FrozenInstanceError):
        seg.id = "m1_00002"


def test_rag_document_construction():
    """Test RagDocument construction with all fields and source_id assertion."""
    doc = RagDocument(
        source_id="doc_1",
        meeting_id="m1",
        segment_index=1,
        title="Meeting Title",
        meeting_date="2026-01-15",
        start_label="00:00:00",
        end_label="00:05:00",
        start_sec=0.0,
        end_sec=300.0,
        text="Discussion about topic",
        source_path="path/to/meeting.webm",
        transcript_txt_path="path/to/transcript.txt",
        transcript_json_path="path/to/transcript.json"
    )
    assert doc.source_id == "doc_1"


def test_rag_answer_construction():
    """Test RagAnswer construction with documents and verify document access."""
    doc = RagDocument(
        source_id="doc_1",
        meeting_id="m1",
        segment_index=1,
        title="Meeting Title",
        meeting_date="2026-01-15",
        start_label="00:00:00",
        end_label="00:05:00",
        start_sec=0.0,
        end_sec=300.0,
        text="Discussion about topic",
        source_path="path/to/meeting.webm",
        transcript_txt_path="path/to/transcript.txt",
        transcript_json_path="path/to/transcript.json"
    )
    answer = RagAnswer(answer="This is the answer", documents=[doc])
    assert answer.documents[0].source_id == "doc_1"
