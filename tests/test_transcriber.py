import json

from meetingkb.config import Settings
from meetingkb.ingest.transcriber import FasterWhisperTranscriber


class _FakeSeg:
    def __init__(self, start, end, text): self.start, self.end, self.text = start, end, text


class _FakeModel:
    def transcribe(self, path, **kw):
        info = type("I", (), {"language": "en", "duration": 6.0})()
        return [_FakeSeg(0.0, 3.0, "Alpha"), _FakeSeg(3.0, 6.0, "Beta")], info


def test_transcribe_file_writes_whisper_json(tmp_path):
    settings = Settings(data_dir=tmp_path)
    media = tmp_path / "meeting.webm"
    media.write_bytes(b"fake")
    t = FasterWhisperTranscriber(settings, model_loader=lambda **kw: _FakeModel())
    out = t.transcribe_file(media)
    assert out == settings.transcript_dir / "meeting.json"
    data = json.loads(out.read_text(encoding="utf-8"))
    assert [s["text"] for s in data["segments"]] == ["Alpha", "Beta"]
    assert data["language"] == "en"
