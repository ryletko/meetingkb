from pathlib import Path

from meetingkb.config import Settings


def test_defaults_derive_from_data_dir(tmp_path):
    s = Settings(data_dir=tmp_path)
    assert s.transcript_dir == tmp_path / "transcripts"
    assert s.db_path == tmp_path / "knowledge.sqlite"
    assert s.os_meetings_index == "meetingkb_meetings"
    assert s.language == "en"


def test_no_project_specific_defaults():
    s = Settings(data_dir=Path("./data"))
    assert s.terms == []
    joined = " ".join([s.rag_system_prompt, s.os_meetings_index, s.os_segments_index])
    for banned in ("Example", "Tracker", "Vendor", "Russian"):
        assert banned not in joined


def test_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("KB_OPENSEARCH_URL", "http://os:9200")
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    s = Settings()
    assert s.opensearch_url == "http://os:9200"
    assert s.db_path == tmp_path / "knowledge.sqlite"


def test_terms_loaded_from_file(tmp_path):
    f = tmp_path / "terms.txt"
    f.write_text("Alpha\nBeta\n\nGamma\n", encoding="utf-8")
    s = Settings(data_dir=tmp_path, terms_file=f)
    assert s.terms == ["Alpha", "Beta", "Gamma"]
