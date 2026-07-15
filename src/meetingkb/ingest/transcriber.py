"""In-process transcription backend, replacing the external whisper.exe batch script.

`FasterWhisperTranscriber` loads its model lazily (on first `transcribe_file`
call) via an injectable `model_loader`, so importing this module — and using a
fake loader in tests — never requires the optional `faster-whisper` extra.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from meetingkb.config import Settings

logger = logging.getLogger(__name__)


class Transcriber(Protocol):
    """Interface for a media -> transcript-JSON backend."""

    def transcribe_file(self, media_path: Path) -> Path: ...


def _load_faster_whisper_model(settings: Settings) -> Any:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError(
            "faster-whisper is not installed. Install it with: "
            'pip install "meetingkb[transcribe]"'
        ) from exc
    return WhisperModel(
        settings.whisper_model,
        device=settings.whisper_device,
        compute_type=settings.whisper_compute_type,
    )


class FasterWhisperTranscriber(Transcriber):
    """Transcribes media files in-process using `faster-whisper`.

    The model is loaded lazily on first `transcribe_file` call via
    `model_loader`, which defaults to importing and constructing a
    `faster_whisper.WhisperModel` from `settings`. Inject a fake `model_loader`
    in tests to avoid depending on the (optional) `faster-whisper` extra.
    """

    def __init__(
        self,
        settings: Settings,
        model_loader: Callable[..., Any] | None = None,
    ) -> None:
        self.settings = settings
        self._model_loader = model_loader or (lambda: _load_faster_whisper_model(settings))
        self._model: Any | None = None

    def _get_model(self) -> Any:
        if self._model is None:
            self._model = self._model_loader()
        return self._model

    def transcribe_file(self, media_path: Path) -> Path:
        model = self._get_model()
        segments, info = model.transcribe(
            str(media_path),
            language=self.settings.language or None,
            initial_prompt=self.settings.initial_prompt or None,
        )
        data = {
            "language": info.language,
            "duration": info.duration,
            "segments": [
                {"start": s.start, "end": s.end, "text": s.text} for s in segments
            ],
        }

        transcript_dir = self.settings.transcript_dir
        assert transcript_dir is not None
        transcript_dir.mkdir(parents=True, exist_ok=True)
        out_path = transcript_dir / f"{media_path.stem}.json"
        out_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return out_path


def transcribe_dir(settings: Settings, transcriber: Transcriber, input_dir: Path) -> list[Path]:
    """Transcribe every media file in `input_dir` whose transcript is missing.

    Returns the list of newly produced transcript paths.
    """
    transcript_dir = settings.transcript_dir
    assert transcript_dir is not None

    produced: list[Path] = []
    for media_path in sorted(input_dir.iterdir(), key=lambda p: p.name.lower()):
        if not media_path.is_file():
            continue
        if media_path.suffix.lower() not in settings.media_extensions:
            continue
        transcript_path = transcript_dir / f"{media_path.stem}.json"
        if transcript_path.exists():
            continue
        produced.append(transcriber.transcribe_file(media_path))
    return produced
