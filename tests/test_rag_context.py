from meetingkb.rag.context import build_context_documents, build_rag_messages


def _loader(meeting_id, idx, before, after):
    return [{"meeting_id": meeting_id, "segment_index": idx, "title": "T",
             "meeting_date": "2026-01-01", "source_path": "/x.webm",
             "transcript_txt_path": "/x.txt", "transcript_json_path": "/x.json",
             "start_label": "00:00:00", "end_label": "00:00:05",
             "start_sec": 0.0, "end_sec": 5.0, "text": "Alpha context"}]


def test_build_documents_assigns_source_ids():
    hits = [{"meeting_id": "m1", "segment_index": 3}]
    docs = build_context_documents(hits, _loader)
    assert docs[0].source_id == "S1"
    assert "Alpha" in docs[0].text


def test_messages_use_injected_prompt_and_cite():
    docs = build_context_documents([{"meeting_id": "m1", "segment_index": 3}], _loader)
    msgs = build_rag_messages("What about Alpha?", docs, system_prompt="NEUTRAL RULES")
    assert len(msgs) == 2
    assert msgs[0]["content"] == "NEUTRAL RULES"
    assert "[S1]" in msgs[1]["content"]
    assert "Example" not in msgs[0]["content"]
