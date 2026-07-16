"""Opt-in background auto-ingest worker: poll data_dir, transcribe, index, thumbnail.

`AutoIngestWorker.run_once()` is the pure, testable unit -- it never raises
(any exception is caught, recorded on `AutoIngestStatus`, and swallowed so a
`run_forever()` loop survives indefinitely). Kept UI-free (no `streamlit`
import) so it can be exercised directly in tests with a fake transcriber and
no threads/sleeps.
"""
from __future__ import annotations

import importlib.util
import logging
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from meetingkb.config import Settings
from meetingkb.ingest.gen_thumbnails import generate_all
from meetingkb.ingest.indexer import build_index
from meetingkb.ingest.transcriber import FasterWhisperTranscriber, Transcriber

logger = logging.getLogger(__name__)


@dataclass
class AutoIngestStatus:
    """UI-facing snapshot of the auto-ingest worker's current state."""

    enabled: bool = False
    watching_dir: str = ""
    last_scan_at: str | None = None
    state: str = "idle"  # "idle" | "transcribing" | "indexing" | "error" | "disabled"
    current_file: str | None = None
    transcribed_count: int = 0
    last_error: str | None = None


class AutoIngestWorker:
    """Polls `settings.data_dir` for new, stable media files and ingests them.

    `run_once()` does a single scan/ingest cycle and never propagates
    exceptions. `run_forever()` loops it on an interval until `stop()` is
    called -- intended to run on a daemon thread started by the Streamlit UI.
    """

    def __init__(
        self,
        settings: Settings,
        transcriber: Transcriber,
        status: AutoIngestStatus | None = None,
        *,
        sleep=time.sleep,
    ) -> None:
        self.settings = settings
        self.transcriber = transcriber
        self.status = status if status is not None else AutoIngestStatus()
        self.status.enabled = True
        self.status.watching_dir = str(settings.data_dir)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._sleep = sleep
        self._seen_sizes: dict[Path, int] = {}

    def _find_candidates(self) -> list[Path]:
        """Media files under data_dir missing a transcript, sorted by name."""
        data_dir = self.settings.data_dir
        transcript_dir = self.settings.transcript_dir
        assert transcript_dir is not None
        if not data_dir.is_dir():
            return []

        candidates = []
        for path in data_dir.iterdir():
            if not path.is_file():
                continue
            if path.suffix.lower() not in self.settings.media_extensions:
                continue
            transcript_path = transcript_dir / f"{path.stem}.json"
            if transcript_path.exists():
                continue
            candidates.append(path)
        return sorted(candidates, key=lambda p: p.name.lower())

    def _stable_files(self, candidates: list[Path]) -> list[Path]:
        """Return the subset of `candidates` whose size matches the previous scan.

        Updates `self._seen_sizes` with every candidate's current size (so a
        brand-new file is recorded this cycle and becomes eligible next cycle
        if its size hasn't changed; a still-growing file keeps getting
        deferred). Files that gained a transcript (dropped out of
        `candidates`) are naturally forgotten below.
        """
        stable: list[Path] = []
        current_sizes: dict[Path, int] = {}
        for path in candidates:
            try:
                size = path.stat().st_size
            except OSError:
                continue
            current_sizes[path] = size
            if self._seen_sizes.get(path) == size:
                stable.append(path)
        self._seen_sizes = current_sizes
        return stable

    def run_once(self) -> None:
        """Run a single scan/transcribe/index cycle. Never raises."""
        try:
            self._run_once_inner()
        except Exception as exc:  # noqa: BLE001 - never propagate; the loop must survive
            logger.exception("auto-ingest cycle failed")
            with self._lock:
                self.status.state = "error"
                self.status.last_error = str(exc)
                self.status.current_file = None

    def _run_once_inner(self) -> None:
        # Only the real FasterWhisperTranscriber needs the optional
        # `faster-whisper` package; an injected fake (e.g. in tests) satisfies
        # the `Transcriber` protocol without it, so it's exempt from this guard.
        needs_faster_whisper = isinstance(self.transcriber, FasterWhisperTranscriber)
        if needs_faster_whisper and importlib.util.find_spec("faster_whisper") is None:
            with self._lock:
                self.status.state = "disabled"
                self.status.last_error = (
                    'faster-whisper is not installed. Install it with: '
                    'pip install "meetingkb[transcribe]"'
                )
            return

        candidates = self._find_candidates()
        stable = self._stable_files(candidates)

        produced = 0
        for path in stable:
            with self._lock:
                self.status.state = "transcribing"
                self.status.current_file = path.name
            self.transcriber.transcribe_file(path)
            produced += 1

        if produced:
            with self._lock:
                self.status.state = "indexing"
                self.status.current_file = None
            build_index(self.settings, use_opensearch=self.settings.opensearch_enabled)
            generate_all(self.settings)
            with self._lock:
                self.status.transcribed_count += produced

        with self._lock:
            self.status.last_scan_at = datetime.now(UTC).isoformat()
            self.status.state = "idle"
            self.status.current_file = None
            self.status.last_error = None

    def run_forever(self) -> None:
        """Run `run_once()` on `settings.auto_ingest_interval`-second intervals until `stop()`."""
        while not self._stop.is_set():
            self.run_once()
            self._sleep(self.settings.auto_ingest_interval)

    def stop(self) -> None:
        self._stop.set()
