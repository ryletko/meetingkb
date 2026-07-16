import json
from pathlib import Path

from meetingkb.config import Settings
from meetingkb.ingest.transcriber import FasterWhisperTranscriber
from meetingkb.ingest.watcher import AutoIngestWorker
from meetingkb.search import storage


class _FakeTranscriber:
    """Writes a minimal valid Whisper-JSON transcript instead of running real Whisper."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.calls: list[Path] = []

    def transcribe_file(self, media_path: Path) -> Path:
        self.calls.append(media_path)
        transcript_dir = self.settings.transcript_dir
        assert transcript_dir is not None
        transcript_dir.mkdir(parents=True, exist_ok=True)
        out = transcript_dir / f"{media_path.stem}.json"
        out.write_text(
            json.dumps(
                {
                    "language": "en",
                    "segments": [{"start": 0.0, "end": 1.0, "text": "hello world"}],
                }
            ),
            encoding="utf-8",
        )
        return out


def test_stable_file_transcribed_then_indexed(tmp_path):
    settings = Settings(data_dir=tmp_path, opensearch_enabled=False)
    media = tmp_path / "meeting.webm"
    media.write_bytes(b"x" * 100)
    fake = _FakeTranscriber(settings)
    worker = AutoIngestWorker(settings, fake)

    # Cycle 1: brand-new file is only recorded, not yet processed.
    worker.run_once()
    assert fake.calls == []
    assert worker.status.transcribed_count == 0
    assert worker.status.state == "idle"

    # Cycle 2: size unchanged since cycle 1 -> stable -> transcribed + indexed.
    worker.run_once()
    assert [c.name for c in fake.calls] == ["meeting.webm"]
    assert worker.status.transcribed_count >= 1
    assert worker.status.state == "idle"
    assert worker.status.last_error is None

    conn = storage.connect(settings.db_path)
    try:
        rows = conn.execute("SELECT id, title FROM meetings").fetchall()
    finally:
        conn.close()
    assert len(rows) == 1
    assert rows[0]["title"] == "meeting"


def test_growing_file_is_deferred_until_stable(tmp_path):
    settings = Settings(data_dir=tmp_path, opensearch_enabled=False)
    media = tmp_path / "growing.mp4"
    media.write_bytes(b"a" * 10)
    fake = _FakeTranscriber(settings)
    worker = AutoIngestWorker(settings, fake)

    # Cycle 1: records the initial size.
    worker.run_once()
    assert fake.calls == []

    # File grows before cycle 2 -> size mismatch -> still deferred.
    media.write_bytes(b"a" * 20)
    worker.run_once()
    assert fake.calls == []

    # Size unchanged since cycle 2 -> now stable -> processed.
    worker.run_once()
    assert [c.name for c in fake.calls] == ["growing.mp4"]
    assert worker.status.transcribed_count >= 1


def test_run_once_noops_when_a_cycle_is_already_active(tmp_path):
    # Simulates the background run_forever() loop and the UI's "Scan now"
    # button racing on the same worker: while a cycle "is running" (lock
    # held), a second run_once() call must return immediately without
    # transcribing or indexing anything.
    settings = Settings(data_dir=tmp_path, opensearch_enabled=False)
    media = tmp_path / "meeting.webm"
    media.write_bytes(b"x" * 100)
    fake = _FakeTranscriber(settings)
    worker = AutoIngestWorker(settings, fake)

    # Prime _seen_sizes so this file would be considered "stable" (i.e. a
    # normal run_once() would transcribe it) if the guard didn't block it.
    worker.run_once()
    assert fake.calls == []

    worker._cycle_lock.acquire()
    try:
        worker.run_once()
    finally:
        worker._cycle_lock.release()

    assert fake.calls == []
    assert worker.status.transcribed_count == 0
    assert not settings.db_path.exists()


def test_missing_faster_whisper_sets_disabled_without_raising(tmp_path):
    # faster-whisper is intentionally not installed in this environment (no
    # [transcribe] extra), so a worker built with the real, non-injected
    # FasterWhisperTranscriber must hit the lazy-import guard.
    settings = Settings(data_dir=tmp_path, opensearch_enabled=False)
    media = tmp_path / "meeting.webm"
    media.write_bytes(b"x" * 100)
    real_transcriber = FasterWhisperTranscriber(settings)
    worker = AutoIngestWorker(settings, real_transcriber)

    worker.run_once()

    assert worker.status.state == "disabled"
    assert worker.status.last_error is not None
    assert "transcribe" in worker.status.last_error
    assert worker.status.transcribed_count == 0
