from __future__ import annotations

import subprocess
from pathlib import Path

THUMB_INTERVAL = 5  # seconds between preview frames
THUMB_W = 160
THUMB_H = 90

_gpu_supported: bool | None = None
_gpu_failed = False


def gpu_available() -> bool:
    """True if this ffmpeg build exposes CUDA hardware decoding (NVIDIA)."""
    global _gpu_supported
    if _gpu_supported is None:
        try:
            out = subprocess.run(
                ["ffmpeg", "-hide_banner", "-hwaccels"],
                capture_output=True, text=True, timeout=15,
            )
            _gpu_supported = "cuda" in (out.stdout or "").lower()
        except Exception:  # noqa: BLE001
            _gpu_supported = False
    return _gpu_supported


def thumbs_dir(root: Path, meeting_id: str) -> Path:
    return Path(root) / "thumbs" / meeting_id


def vtt_path(root: Path, meeting_id: str) -> Path:
    return thumbs_dir(root, meeting_id) / "storyboard.vtt"


def has_thumbnails(root: Path, meeting_id: str) -> bool:
    p = vtt_path(root, meeting_id)
    return p.is_file() and p.stat().st_size > 0


def _vtt_timestamp(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


def generate(
    root: Path,
    meeting_id: str,
    video_path: Path,
    interval: int = THUMB_INTERVAL,
    force: bool = False,
    gpu: bool = True,
) -> Path | None:
    """Generate thumbnail JPEGs + a WebVTT index for one meeting. Returns the VTT path.

    Decoding runs on the NVIDIA GPU (``-hwaccel cuda``) when available so the CPU
    stays free for the app; it falls back to CPU decoding automatically.
    """
    global _gpu_failed
    video_path = Path(video_path)
    if not video_path.is_file():
        return None
    out = thumbs_dir(root, meeting_id)
    vtt = vtt_path(root, meeting_id)
    if not force and vtt.is_file() and vtt.stat().st_size > 0:
        return vtt

    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("thumb-*.jpg"):
        old.unlink()

    vf = (
        f"fps=1/{interval},"
        f"scale={THUMB_W}:{THUMB_H}:force_original_aspect_ratio=decrease,"
        f"pad={THUMB_W}:{THUMB_H}:(ow-iw)/2:(oh-ih)/2:color=black"
    )

    def _run(use_gpu: bool):
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
        if use_gpu:
            cmd += ["-hwaccel", "cuda"]  # GPU decode keeps the CPU free
        cmd += [
            "-i", str(video_path),
            "-vf", vf, "-an",
            "-q:v", "5", "-start_number", "0",
            str(out / "thumb-%05d.jpg"),
        ]
        return subprocess.run(cmd, capture_output=True, text=True)

    want_gpu = gpu and not _gpu_failed and gpu_available()
    result = _run(want_gpu)
    if want_gpu and result.returncode != 0:
        # GPU path failed (unsupported codec / driver) — use CPU for this and the rest.
        _gpu_failed = True
        for old in out.glob("thumb-*.jpg"):
            old.unlink()
        result = _run(False)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or "ffmpeg failed").strip()[:400] or "ffmpeg failed")

    frames = sorted(out.glob("thumb-*.jpg"))
    if not frames:
        return None
    lines = ["WEBVTT", ""]
    for i, frame in enumerate(frames):
        lines.append(f"{_vtt_timestamp(i * interval)} --> {_vtt_timestamp((i + 1) * interval)}")
        lines.append(frame.name)
        lines.append("")
    vtt.write_text("\n".join(lines), encoding="utf-8")
    return vtt
